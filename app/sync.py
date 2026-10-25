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
from scraper.extract import parse_detail, parse_listing
from scraper.http import HttpClient
from app.adapters.ask4movie import catalog as a4m_catalog
from app.adapters.ask4movie.http import get as a4m_get
from app.adapters.ask4movie.sync import upsert as a4m_upsert

logger = logging.getLogger("cinemymovies.sync")

# Global state for sync status reporting
_LAST_SYNC_META = {
    "last_run": None,
    "status": "idle",
    "details": None,
}

YOMOVIES_PAGES = [
    # (relative_path, max_pages)
    ("/", 1),                      # Homepage featured & latest
    ("/release-year/2026/", 2),    # Current year releases
    ("/genre/bollywood/", 1),      # Latest Bollywood
    ("/genre/punjabi/", 1),        # Latest Punjabi
    ("/genre/web-series/", 1),     # Latest Series
    ("/movies/", 1),               # General movies
]

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

    # Check if exists
    cur = conn.cursor()
    cur.execute("SELECT id FROM movies WHERE url=? OR detail_url=? OR (source='yomovies' AND source_id=?)",
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
        "player_kind": "hls",
        "is_hindi_dubbed": is_dubbed,
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

        set_clause = ", ".join(f"{k}=:{k}" for k in data.keys() if k not in ("id", "slug", "source", "source_id"))
        conn.execute(f"UPDATE movies SET {set_clause} WHERE id={movie_id}", data)

    conn.commit()
    return is_new


def sync_yomovies(base_time: int) -> Dict[str, int]:
    """Sync latest items from Yomovies."""
    base_url = SITE_MIRRORS[0] if SITE_MIRRORS else "https://yomovies.wine"
    http = HttpClient(delay=0.1, cache_dir=".cache")

    print(f"[sync-yomovies] Scraping latest items from {base_url}...", flush=True)

    urls_ordered: List[str] = []
    seen: set = set()

    for path, max_p in YOMOVIES_PAGES:
        for p in range(1, max_p + 1):
            if path == "/":
                url = base_url if p == 1 else f"{base_url}/page/{p}/"
            else:
                url = f"{base_url}{path}" if p == 1 else f"{base_url}{path}page/{p}/"
            try:
                html = http.get(url, force=True)
                cards = parse_listing(html, base_url)
                new_in_page = 0
                for c in cards:
                    u = c.get("url")
                    if u and u not in seen:
                        seen.add(u)
                        urls_ordered.append(u)
                        new_in_page += 1
                print(f"[sync-yomovies] [{path} p.{p}] Found {len(cards)} items ({new_in_page} new)", flush=True)
            except Exception as e:
                print(f"[sync-yomovies] Error fetching {url}: {e}", flush=True)

    print(f"[sync-yomovies] Total unique URLs to ingest/refresh: {len(urls_ordered)}", flush=True)

    db_paths = get_target_db_paths()
    conns = [sqlite3.connect(p, timeout=30) for p in db_paths]

    added = 0
    updated = 0

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
            if existing_row and existing_row.get("embeds") and existing_row.get("embeds") != "[]" and existing_row.get("synopsis"):
                # Fast path: title already scraped with full embeds & synopsis
                info = existing_row
                for k in ("genres", "actors", "director", "country", "embeds", "downloads"):
                    if isinstance(info.get(k), str):
                        try:
                            info[k] = json.loads(info[k])
                        except Exception:
                            pass
            else:
                # Scrape detail page
                html = http.get(u, force=True)
                info = parse_detail(html, u)

            if not info or not info.get("title"):
                continue

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

    duration = round(time.time() - start_time, 2)
    summary = {
        "status": "success",
        "duration_seconds": duration,
        "timestamp": base_time,
        "yomovies": ym_res,
        "ask4movie": a4m_res,
        "total_added": ym_res["added"] + a4m_res["added"],
        "total_refreshed": ym_res["updated"] + a4m_res["updated"],
    }

    _LAST_SYNC_META["last_run"] = base_time
    _LAST_SYNC_META["status"] = "idle"
    _LAST_SYNC_META["details"] = summary

    print("=" * 60)
    print(f"[SYNC] Finished in {duration}s! Total New: {summary['total_added']}, Total Refreshed: {summary['total_refreshed']}")
    print("=" * 60)
    return summary


def get_sync_status() -> Dict[str, Any]:
    return dict(_LAST_SYNC_META)


if __name__ == "__main__":
    run_full_sync()
