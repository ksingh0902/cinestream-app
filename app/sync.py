"""Unified Catalog Sync Engine for CineMyMovies.

Fetches newly released titles from both Yomovies and Ask4movie,
enriches them with metadata/embeds, and upserts them into
cinemymovies.sqlite3 and yomovies.db with recency ordering.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import SITE_MIRRORS
from scraper.extract import parse_detail, parse_listing, parse_pagination, is_erotic_content
from scraper.http import HttpClient
from app.adapters.ask4movie import catalog as a4m_catalog
from app.adapters.ask4movie.http import get as a4m_get
from app.adapters.ask4movie.sync import upsert as a4m_upsert
from app.adapters.movies7.sync import sync_movies7

logger = logging.getLogger("cinemymovies.sync")

# Global state for sync status reporting
_LAST_SYNC_META = {
    "last_run": None,
    "status": "idle",
    "details": None,
}

YOMOVIES_OTT_PAGES = [
    ("/director/netflix/", 3),
    ("/director/amazon-prime/", 3),
    ("/director/hotstar/", 3),
    ("/director/zee5/", 2),
    ("/director/sonyliv-original/", 2),
]

YOMOVIES_PAGES = [
    # (relative_path, max_pages)
    ("/", 3),                      # Homepage featured & latest
    ("/movies/", 3),               # General movies
    ("/genre/bollywood/", 2),      # Latest Bollywood
    ("/genre/hollywood/", 2),      # Latest Hollywood
    ("/genre/hollywood-dubbed/", 2), # Latest Hollywood Hindi Dubbed
    ("/genre/dual-audio/", 2),     # Latest Dual Audio
    ("/genre/south-special/", 2),  # Latest South Indian Dubbed
    ("/series/", 3),               # English & International TV Series
    ("/genre/web-series/", 2),     # Hindi Dubbed & Regional Web Series
    ("/genre/tv-shows/", 2),       # TV Shows
    ("/release-year/2026/", 3),    # Current year releases
    ("/release-year/2025/", 2),    # Previous year new uploads
    ("/genre/animation/", 3),      # Latest Animation additions
    ("/genre/punjabi/", 2),        # Latest Punjabi
    ("/genre/top-rated/", 2),      # Mostly watched / Top rated
] + YOMOVIES_OTT_PAGES

YOMOVIES_FORCED_GENRES = {
    "/genre/animation/": "Animation",
    "/director/netflix/": "Netflix",
    "/director/amazon-prime/": "Amazon Prime",
    "/director/zee5/": "Zee5",
    "/director/hotstar/": "Hotstar",
    "/director/sonyliv-original/": "Sony Liv",
}

ASK4MOVIE_URLS = [
    "https://fbox.gd/movie?page=1",
    "https://fbox.gd/movie?page=2",
    "https://fbox.gd/tv?page=1",
    "https://fbox.gd/tv?page=2",
    "https://fbox.gd/latest",
    "https://fbox.gd/trending",
]


def get_target_db_paths() -> List[str]:
    paths = []
    if os.path.exists("cinemymovies.sqlite3"):
        paths.append("cinemymovies.sqlite3")
    if os.path.exists("yomovies.db"):
        paths.append("yomovies.db")
    if not paths:
        paths.append("cinemymovies.sqlite3")
    return paths


def _is_hindi_dubbed(title: str, genres: list, quality: str) -> bool:
    t = (title or "").lower()
    g_str = " ".join([str(x).lower() for x in genres]) if genres else ""
    q = (quality or "").lower()
    if any(k in g_str for k in ("hollywood dubbed", "dual audio", "unofficial dubbed", "hindi dubbed")):
        return True
    if any(k in t for k in ("hindi dubbed", "dual audio", "(hindi)", "[hindi]", "dual-audio")):
        return True
    if q in ("hindi", "dual audio"):
        return True
    return False


def upsert_yomovies_item(conn: sqlite3.Connection, m: Dict[str, Any], updated_at: int) -> bool:
    """Upsert a Yomovies media dictionary into the database."""
    # Strictly reject excluded content
    if is_erotic_content(m):
        logger.info("Skipping excluded title: %s (%s)", m.get("title"), m.get("url"))
        return False

    title = m.get("title") or ""
    if any(k in title.lower() for k in ("gateway time-out", "error code", "504 gateway", "just a moment", "404 not found")):
        logger.info("Skipping error page: %s", title)
        return False

    url = m.get("url") or ""
    slug = (url.rstrip("/").rsplit("/", 1)[-1] or None) if url else None
    title = m.get("title") or ""
    genres = m.get("genres") or []
    if isinstance(genres, str):
        try:
            genres = json.loads(genres)
        except Exception:
            genres = [g.strip() for g in genres.split(",") if g.strip()]

    # Normalize Punjabi tag
    if "/genre/punjabi/" in url or "punjabi" in title.lower():
        if not any("punjabi" in str(x).lower() for x in genres):
            genres.append("Punjabi")

    quality = m.get("quality") or ""
    is_dubbed = 1 if _is_hindi_dubbed(title, genres, quality) else 0

    # Parse rating
    rating = None
    imdb_str = str(m.get("imdb") or "")
    if imdb_str:
        try:
            cleaned = imdb_str.replace("IMDb: ", "").replace("★ ", "").strip()
            rating = float(cleaned)
        except Exception:
            pass

    embeds = m.get("embeds") or []
    downloads = m.get("downloads") or []
    poster = m.get("poster") or ""
    synopsis = m.get("synopsis") or ""
    year = str(m.get("year") or "")
    duration = str(m.get("duration") or "")
    is_series = int(m.get("is_series") or 0)
    tmdb_id = str(m.get("tmdb_id") or "") or None

    has_speedo = any(e.get("type") == "speedo" or "speedo" in (e.get("host") or "").lower() for e in embeds)
    player_kind = "hls" if (has_speedo or not embeds) else "iframe"

    # Check if exists
    cur = conn.cursor()
    cur.execute("SELECT id, tmdb_id FROM movies WHERE url=? OR detail_url=? OR (source='yomovies' AND source_id=?)",
                (url, url, slug))
    existing = cur.fetchone()
    is_new = existing is None

    data = {
        "slug": slug,
        "url": url,
        "title": title,
        "year": year,
        "duration": duration,
        "duration_s": m.get("duration_s"),
        "quality": quality,
        "imdb": m.get("imdb"),
        "genres": json.dumps(genres),
        "actors": json.dumps(m.get("actors") or []),
        "director": json.dumps(m.get("director") or []),
        "country": json.dumps(m.get("country") or []),
        "poster": poster,
        "synopsis": synopsis,
        "is_series": is_series,
        "embeds": json.dumps(embeds),
        "downloads": json.dumps(downloads),
        "updated_at": updated_at,
        "source": "yomovies",
        "source_id": slug or "",
        "poster_url": poster,
        "rating": rating,
        "detail_url": url,
        "player_kind": player_kind,
        "is_hindi_dubbed": is_dubbed,
        "tmdb_id": tmdb_id or (existing[1] if existing else None),
    }

    if is_new:
        cols = ", ".join(data.keys())
        placeholders = ", ".join(f":{k}" for k in data.keys())
        conn.execute(f"INSERT INTO movies ({cols}) VALUES ({placeholders})", data)
    else:
        movie_id = existing[0]
        # Keep embeds if existing row has them and scraped doesn't
        if not embeds:
            cur.execute("SELECT embeds FROM movies WHERE id=?", (movie_id,))
            old_embs = cur.fetchone()[0]
            if old_embs and old_embs != "[]":
                data["embeds"] = old_embs

        # Retain all existing genres / platform tags so multi-platform titles keep every applicable tag
        cur.execute("SELECT genres FROM movies WHERE id=?", (movie_id,))
        old_genres_row = cur.fetchone()
        if old_genres_row and old_genres_row[0]:
            try:
                old_genres_list = json.loads(old_genres_row[0]) if isinstance(old_genres_row[0], str) else old_genres_row[0]
            except Exception:
                old_genres_list = [g.strip() for g in str(old_genres_row[0]).split(",") if g.strip()]

            merged_genres = list(genres)
            existing_lower = {str(g).lower() for g in merged_genres}
            for old_g in old_genres_list:
                if str(old_g).lower() not in existing_lower:
                    merged_genres.append(old_g)
                    existing_lower.add(str(old_g).lower())
            data["genres"] = json.dumps(merged_genres)

        set_clause = ", ".join(f"{k}=:{k}" for k in data.keys() if k not in ("id", "slug", "source", "source_id"))
        conn.execute(f"UPDATE movies SET {set_clause} WHERE id={movie_id}", data)

    conn.commit()
    return is_new


def sync_yomovies(
    base_time: int,
    pages: list[tuple[str, int]] | None = None,
    base_url: str | None = None,
    base_urls: list[str] | None = None,
    enrich_details: bool = True,
    force_refresh: bool = True,
) -> Dict[str, int]:
    """Sync latest items from Yomovies & PRmovies mirrors into unified Yomovies catalogue."""
    if base_urls:
        target_bases = [b.rstrip("/") for b in base_urls if b]
    elif base_url:
        target_bases = [base_url.rstrip("/")]
    else:
        # Default to PRmovies (original/parent mirror) and Yomovies active mirror
        target_bases = ["https://prmovies.ventures", "https://yomovies.com.im"]

    http = HttpClient(delay=0.1, cache_dir=".cache")

    print(f"[sync-yomovies] Scraping latest items from mirrors: {', '.join(target_bases)}...", flush=True)

    urls_ordered: List[str] = []
    seen: set = set()
    seen_slugs: set = set()
    forced_genres_by_url: Dict[str, set[str]] = {}
    listing_by_url: Dict[str, Dict[str, Any]] = {}

    for current_base in target_bases:
        print(f"[sync-yomovies] Checking mirror: {current_base}", flush=True)
        for path, max_p in (pages or YOMOVIES_PAGES):
            for p in range(1, max_p + 1):
                if path == "/":
                    url = current_base if p == 1 else f"{current_base}/page/{p}/"
                else:
                    url = f"{current_base}{path}" if p == 1 else f"{current_base}{path}page/{p}/"
                try:
                    html = http.get(url, force=force_refresh)
                    cards = parse_listing(html, current_base)
                    if not cards:
                        break
                    new_in_page = 0
                    for c in cards:
                        if is_erotic_content(c):
                            continue
                        u = c.get("url")
                        if not u:
                            continue
                        slug = (u.rstrip("/").rsplit("/", 1)[-1] or "").lower()
                        forced_genre = YOMOVIES_FORCED_GENRES.get(path)
                        if forced_genre:
                            forced_genres_by_url.setdefault(u, set()).add(forced_genre)
                            genres = c.get("genres") or []
                            if not any(str(g).lower() == forced_genre.lower() for g in genres):
                                genres.append(forced_genre)
                            c["genres"] = genres

                        if u in listing_by_url:
                            prev_genres = listing_by_url[u].get("genres") or []
                            cur_genres = c.get("genres") or []
                            merged_card_genres = list(prev_genres)
                            existing_g_lower = {str(g).lower() for g in merged_card_genres}
                            for g in cur_genres:
                                if str(g).lower() not in existing_g_lower:
                                    merged_card_genres.append(g)
                                    existing_g_lower.add(str(g).lower())
                            c["genres"] = merged_card_genres
                        listing_by_url[u] = c

                        if u not in seen and slug not in seen_slugs:
                            seen.add(u)
                            if slug:
                                seen_slugs.add(slug)
                            urls_ordered.append(u)
                            new_in_page += 1
                    print(f"[sync-yomovies] [{current_base} | {path} p.{p}] Found {len(cards)} items ({new_in_page} new)", flush=True)
                    if p < max_p and not parse_pagination(html, current_base):
                        break
                except Exception as e:
                    print(f"[sync-yomovies] Error fetching {url}: {e}", flush=True)
                    break

    print(f"[sync-yomovies] Total unique URLs to ingest/refresh: {len(urls_ordered)}", flush=True)

    db_paths = get_target_db_paths()
    conns = [sqlite3.connect(p, timeout=30) for p in db_paths]

    added = 0
    updated = 0

    if not enrich_details:
        for idx, u in enumerate(urls_ordered):
            info = listing_by_url.get(u)
            if not info or not info.get("title"):
                continue

            t_low = info.get("title", "").lower()
            if any(k in t_low for k in ("gateway time-out", "error code", "504", "just a moment", "404 not found")):
                continue
            genres = info.get("genres") or []
            existing_genres = {str(genre).lower() for genre in genres}
            for forced_genre in forced_genres_by_url.get(u, set()):
                if forced_genre.lower() not in existing_genres:
                    genres.append(forced_genre)
                    existing_genres.add(forced_genre.lower())
            info["genres"] = genres
            is_new_overall = False
            for conn in conns:
                if upsert_yomovies_item(conn, info, base_time - idx):
                    is_new_overall = True
            if is_new_overall:
                added += 1
            else:
                updated += 1
        for conn in conns:
            conn.close()
        http.close()
        print(f"[sync-yomovies] Catalogue import finished: {added} added, {updated} refreshed.", flush=True)
        return {"added": added, "updated": updated, "total": len(urls_ordered)}

    for idx, u in enumerate(urls_ordered):
        try:
            slug = (u.rstrip("/").rsplit("/", 1)[-1] or None) if u else None
            # Check if any db already has this movie with embeds
            existing_row = None
            for conn in conns:
                conn.row_factory = sqlite3.Row
                r = conn.execute(
                    "SELECT * FROM movies WHERE url=? OR detail_url=? OR slug=? OR (source='yomovies' AND source_id=?)",
                    (u, u, slug, slug)
                ).fetchone()
                if r:
                    existing_row = dict(r)
                    break

            info = None
            if existing_row:
                # Fast path: title already in catalogue, refresh recency order
                info = existing_row
                for k in ("genres", "actors", "director", "country", "embeds", "downloads"):
                    if isinstance(info.get(k), str):
                        try:
                            info[k] = json.loads(info[k])
                        except Exception:
                            pass
            else:
                # Newly added title: scrape detail page with full embeds & metadata
                html = http.get(u, force=True)
                info = parse_detail(html, u)
                if info and info.get("is_series") and not info.get("embeds") and info.get("episodes"):
                    try:
                        ep_url = info["episodes"][0]
                        ep_html = http.get(ep_url, force=True)
                        ep_info = parse_detail(ep_html, ep_url)
                        if ep_info.get("embeds"):
                            info["embeds"] = ep_info["embeds"]
                        if not info.get("tmdb_id") and ep_info.get("tmdb_id"):
                            info["tmdb_id"] = ep_info["tmdb_id"]
                    except Exception as e_ep:
                        logger.debug("Failed fetching series episode embeds: %s", e_ep)

            if not info or not info.get("title"):
                continue

            t_low = info.get("title", "").lower()
            if any(k in t_low for k in ("gateway time-out", "error code", "504", "just a moment", "404 not found")):
                continue

            forced_genres = forced_genres_by_url.get(u, set())
            if forced_genres:
                info_genres = info.get("genres") or []
                if isinstance(info_genres, str):
                    try:
                        info_genres = json.loads(info_genres)
                    except Exception:
                        info_genres = [g.strip() for g in info_genres.split(",") if g.strip()]
                existing_genres = {str(g).lower() for g in info_genres}
                for forced_genre in forced_genres:
                    if forced_genre.lower() not in existing_genres:
                        info_genres.append(forced_genre)
                info["genres"] = info_genres

            # Preserves top-to-bottom sequence on Yomovies homepage:
            # Earlier items on page 1 get higher updated_at timestamps
            recency_timestamp = base_time - idx

            is_new_overall = False
            for conn in conns:
                was_new = upsert_yomovies_item(conn, info, recency_timestamp)
                if was_new:
                    is_new_overall = True

            embs_count = len(info.get("embeds") or [])
            if is_new_overall:
                added += 1
                print(f"[sync-yomovies] + ADDED: {info['title']} ({info.get('year')}) [{embs_count} embeds]", flush=True)
            else:
                updated += 1
                if idx < 10:
                    print(f"[sync-yomovies] ~ REFRESHED: {info['title']} ({info.get('year')})", flush=True)

        except Exception as e:
            print(f"[sync-yomovies] Error ingesting {u}: {e}", flush=True)

    for conn in conns:
        conn.close()
    http.close()

    print(f"[sync-yomovies] Finished: {added} new titles added, {updated} refreshed.", flush=True)
    return {"added": added, "updated": updated, "total": len(urls_ordered)}


def sync_ask4movie(base_time: int) -> Dict[str, int]:
    """Sync latest items from Ask4movie (fbox.gd)."""
    print("[sync-ask4movie] Scraping latest items from Ask4movie...", flush=True)
    items = []
    seen = set()

    for url in ASK4MOVIE_URLS:
        try:
            r = a4m_get(url)
            parsed = a4m_catalog.parse_listing(r.text)
            for it in parsed:
                if it.source_id not in seen:
                    seen.add(it.source_id)
                    items.append(it)
        except Exception as e:
            print(f"[sync-ask4movie] Error fetching {url}: {e}", flush=True)

    print(f"[sync-ask4movie] Total unique Ask4movie items found: {len(items)}", flush=True)

    db_paths = get_target_db_paths()
    conns = [sqlite3.connect(p, timeout=30) for p in db_paths]

    added = 0
    updated = 0

    for idx, it in enumerate(items):
        try:
            # Preserves order: earlier items get higher recency timestamp
            recency_timestamp = base_time - idx

            for conn in conns:
                cur = conn.cursor()
                cur.execute("SELECT id FROM movies WHERE source='ask4movie' AND source_id=?", (it.source_id,))
                exists = cur.fetchone() is not None

                a4m_upsert(conn, it)
                # Ensure updated_at is set for recency interleaving
                conn.execute(
                    "UPDATE movies SET updated_at=? WHERE source='ask4movie' AND source_id=?",
                    (recency_timestamp, it.source_id)
                )
                conn.commit()

            if exists:
                updated += 1
            else:
                added += 1
                print(f"[sync-ask4movie] + ADDED: {it.title} ({it.year})", flush=True)

        except Exception as e:
            print(f"[sync-ask4movie] Error upserting {it.source_id}: {e}", flush=True)

    for conn in conns:
        conn.close()

    print(f"[sync-ask4movie] Finished: {added} new titles added, {updated} refreshed.", flush=True)
    return {"added": added, "updated": updated, "total": len(items)}


def run_full_sync() -> Dict[str, Any]:
    """Run full catalog sync across both sources."""
    global _LAST_SYNC_META
    _LAST_SYNC_META["status"] = "running"
    start_time = time.time()
    base_time = int(start_time)

    print("=" * 60)
    print("[SYNC] CineMyMovies Automated Catalog Sync Started")
    print("=" * 60)

    ym_res = sync_yomovies(base_time)
    a4m_res = sync_ask4movie(base_time)
    m7_res = sync_movies7(pages_per_category=5)

    duration = round(time.time() - start_time, 2)
    summary = {
        "status": "success",
        "duration_seconds": duration,
        "timestamp": base_time,
        "yomovies": ym_res,
        "ask4movie": a4m_res,
        "movies7": m7_res,
        "total_added": ym_res["added"] + a4m_res["added"] + m7_res.get("total", 0),
        "total_refreshed": ym_res["updated"] + a4m_res["updated"],
    }

    _LAST_SYNC_META["last_run"] = base_time
    _LAST_SYNC_META["status"] = "idle"
    _LAST_SYNC_META["details"] = summary

    print("=" * 60)
    print(f"[SYNC] Finished in {duration}s! Total New: {summary['total_added']}, Total Refreshed: {summary['total_refreshed']}")
    print("=" * 60)

    try:
        from app.api.routes_catalog import invalidate_catalog_cache, prewarm_catalog_cache
        invalidate_catalog_cache()
        prewarm_catalog_cache()
    except Exception as exc:
        print(f"[SYNC] Note: catalog cache invalidation skipped: {exc}", flush=True)

    return summary


def get_sync_status() -> Dict[str, Any]:
    return dict(_LAST_SYNC_META)


if __name__ == "__main__":
    run_full_sync()
