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
from app.catalogue.quality import (
    extract_print_quality,
    is_quality_downgrade,
    is_quality_upgrade,
)
from app.adapters.ask4movie import catalog as a4m_catalog
from app.adapters.ask4movie.http import get as a4m_get
from app.adapters.ask4movie.sync import upsert as a4m_upsert
from app.adapters.movies7.sync import sync_movies7
from app.adapters.dooflix.sync import sync_dooflix
from app.adapters.flixmovie.sync import sync_flixmovie
from app.adapters.moviesdrive.sync import sync_moviesdrive

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


YOMOVIES_PRIORITY_RECHECK_PATHS = {
    "/",
    "/movies/",
    "/genre/bollywood/",
    "/genre/hollywood/",
    "/genre/hollywood-dubbed/",
    "/genre/dual-audio/",
    "/genre/south-special/",
    "/genre/punjabi/",
    "/release-year/2026/",
    "/release-year/2025/",
}
YOMOVIES_RECHECK_INTERVAL_SECS = 24 * 3600
YOMOVIES_RECENT_UPGRADE_WINDOW_SECS = 120 * 86400
YOMOVIES_MAX_RECHECKS_PER_RUN = 80

_ROMAN_TO_ARABIC = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}
_STRIP_TITLE_NOISE_RE = re.compile(
    r"(?:"
    r"\s*[\[(]\s*(?:19|20)\d{2}\s*[\])]"
    r"|\s*[\[(]\s*(?:netflix|amazon\s*prime|prime\s*video|hotstar(?:\s*specials)?|zee5|sonyliv(?:\s*original)?|jio\s*cinema|apple\s*tv\+?|hbo|disney\+?|altbalaji)\s*[\])]"
    r"|\b(?:hindi\s*dubbed|dual\s*audio|in\s*hindi|unofficial\s*dubbed|watch\s*online\s*full\s*movie|full\s*movie)\b"
    r"|\b(?:2160p|4k|uhd|1080p|fhd|720p|web-?dl|webrip|bluray|bdrip|brrip|hdrip|hdcam|camrip|hdts|pre-?dvd|dvdscr|telesync|telecine|cinema|cam|ts|sd|hd)\b"
    r")",
    re.I,
)


def _extract_embed_codes(embeds_val: Any) -> List[str]:
    """Extract normalized playable embed identifiers (e.g. Speedostream video codes or iframe URLs)."""
    if not embeds_val:
        return []
    items = embeds_val
    if isinstance(embeds_val, str):
        try:
            items = json.loads(embeds_val)
        except Exception:
            return []
    if not isinstance(items, list):
        return []
    codes: List[str] = []
    seen: set[str] = set()
    for item in items:
        sig = ""
        if isinstance(item, dict):
            code = str(item.get("code") or "").strip().lower()
            url = str(item.get("url") or "").strip().lower()
            host = str(item.get("host") or "").strip().lower()
            if code and code != "embed":
                sig = f"{host}:{code}" if host else code
            elif url:
                sig = url
        elif isinstance(item, str) and item.strip():
            sig = item.strip().lower()
        if sig and sig not in seen:
            seen.add(sig)
            codes.append(sig)
    return codes


def _yomovies_canonical_signature(
    title: Optional[str],
    year: Optional[str],
    is_series: int,
) -> Optional[tuple[str, str, int, str, str]]:
    """
    Conservative canonical identity for same-source YoMovies matching:
      (normalized_base_title, exact_4_digit_year, is_series, season_num, part_or_sequel)
    Never merges across different years, sequels/parts, seasons, or movie-vs-series.
    """
    raw_title = str(title or "").strip()
    if not raw_title:
        return None

    # Resolve exact 4-digit year (required for conservative canonical fallback matching)
    yr_str = str(year or "").strip()
    m_yr = re.search(r"\b((?:19|20)\d{2})\b", yr_str)
    if not m_yr:
        m_yr = re.search(r"[\[(]\s*((?:19|20)\d{2})\s*[\])]", raw_title)
    if not m_yr:
        return None
    exact_year = m_yr.group(1)

    t_low = raw_title.lower()

    # Extract season number (strictly distinguishes Season 1 vs Season 2)
    season = ""
    m_season = re.search(r"\bseason\s*(\d{1,2})\b|\bs(\d{1,2})\b", t_low)
    if m_season:
        season = str(int(m_season.group(1) or m_season.group(2)))
        t_low = re.sub(r"\bseason\s*\d{1,2}\b|\bs\d{1,2}\b", " ", t_low)

    # Strip year, OTT platform labels, dubbed/language suffixes, and print-quality tokens
    cleaned = _STRIP_TITLE_NOISE_RE.sub(" ", t_low)
    # Remove trailing standalone year if still present
    cleaned = re.sub(rf"\b{re.escape(exact_year)}\b", " ", cleaned)

    # Extract explicit part / chapter / volume indicator
    sequel = ""
    m_part = re.search(r"\b(?:part|vol(?:ume)?|chapter)\s*(\d+|i{1,3}|iv|v|vi)\b", cleaned)
    if m_part:
        tok = m_part.group(1).lower()
        sequel = _ROMAN_TO_ARABIC.get(tok, str(int(tok)) if tok.isdigit() else tok)
        cleaned = cleaned[:m_part.start()] + " " + cleaned[m_part.end():]

    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Extract trailing standalone sequel number / Roman numeral (e.g. "hanuman ansh 2")
    if not sequel:
        m_seq = re.search(r"\s+(\d{1,2}|ii|iii|iv|v|vi)$", cleaned)
        if m_seq:
            tok = m_seq.group(1).lower()
            sequel = _ROMAN_TO_ARABIC.get(tok, str(int(tok)) if tok.isdigit() else tok)
            cleaned = cleaned[:m_seq.start()].strip()

    if not cleaned:
        return None
    return (cleaned, exact_year, int(is_series or 0), season, sequel)


def _find_existing_yomovies_row(
    conn: sqlite3.Connection,
    url: str,
    slug: Optional[str],
    title: Optional[str] = None,
    year: Optional[str] = None,
    is_series: int = 0,
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Look up an existing YoMovies row strictly within source='yomovies':
      1. Exact match by url, detail_url, slug, or (source='yomovies', source_id=slug)
      2. Conservative canonical match (same base title, exact year, is_series, season, sequel)
         to catch YoMovies '-2' / '-3' reposts without merging different movies/sequels/seasons.
    Returns (row_dict, match_kind) where match_kind is 'exact', 'canonical', or None.
    """
    prev_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute(
            "SELECT * FROM movies WHERE (url=? OR detail_url=? OR slug=? OR (source='yomovies' AND source_id=?)) AND COALESCE(source, 'yomovies')='yomovies' LIMIT 1",
            (url, url, slug, slug),
        ).fetchone()
        if r:
            return dict(r), "exact"

        sig = _yomovies_canonical_signature(title, year, is_series)
        if not sig:
            return None, None
        base_title, exact_year, is_s, _, _ = sig
        first_token = base_title.split(" ", 1)[0]
        if len(first_token) < 2:
            return None, None

        candidates = conn.execute(
            """
            SELECT * FROM movies
            WHERE COALESCE(source, 'yomovies') = 'yomovies'
              AND COALESCE(is_series, 0) = ?
              AND (year = ? OR title LIKE ?)
              AND LOWER(title) LIKE ?
            ORDER BY COALESCE(first_added_at, updated_at, id) ASC, id ASC
            LIMIT 40
            """,
            (is_s, exact_year, f"%{exact_year}%", f"%{first_token}%"),
        ).fetchall()
        for cand in candidates:
            cand_dict = dict(cand)
            cand_sig = _yomovies_canonical_signature(
                cand_dict.get("title"),
                cand_dict.get("year"),
                int(cand_dict.get("is_series") or 0),
            )
            if cand_sig == sig:
                return cand_dict, "canonical"
        return None, None
    finally:
        conn.row_factory = prev_factory


def _should_recheck_yomovies_detail(
    existing_row: Dict[str, Any],
    listing_card: Optional[Dict[str, Any]],
    *,
    is_page_one_priority: bool,
    is_canonical_repost: bool,
    now_ts: int,
) -> bool:
    """Bounded detail-page re-check policy for existing YoMovies rows."""
    if is_canonical_repost:
        return True
    if not _extract_embed_codes(existing_row.get("embeds")):
        return True
    if listing_card:
        old_q = str(existing_row.get("quality") or "").strip().lower()
        new_q = str(listing_card.get("quality") or "").strip().lower()
        if new_q and new_q != old_q:
            return True
        old_t = str(existing_row.get("title") or "").strip().lower()
        new_t = str(listing_card.get("title") or "").strip().lower()
        if new_t and new_t != old_t:
            return True
    if is_page_one_priority:
        last_checked = int(existing_row.get("last_checked_at") or existing_row.get("updated_at") or 0)
        first_added = int(existing_row.get("first_added_at") or existing_row.get("updated_at") or 0)
        age_since_check = now_ts - last_checked if last_checked > 0 else YOMOVIES_RECHECK_INTERVAL_SECS + 1
        is_recent_movie = (now_ts - first_added) <= YOMOVIES_RECENT_UPGRADE_WINDOW_SECS if first_added > 0 else True
        if is_recent_movie and age_since_check >= YOMOVIES_RECHECK_INTERVAL_SECS:
            return True
        if age_since_check >= YOMOVIES_RECHECK_INTERVAL_SECS * 2:
            return True
    return False


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


def upsert_yomovies_item(
    conn: sqlite3.Connection,
    m: Dict[str, Any],
    updated_at: int,
    *,
    status_out: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Upsert a YoMovies media dictionary into the database with conservative canonical matching,
    embed/version replacement, genuine print-quality upgrade detection, and downgrade protection.
    Returns True if a brand-new row was inserted, False if an existing YoMovies row was updated/checked.
    """
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

    quality = str(m.get("quality") or "").strip()
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
    if isinstance(embeds, str):
        try:
            embeds = json.loads(embeds)
        except Exception:
            embeds = []
    downloads = m.get("downloads") or []
    if isinstance(downloads, str):
        try:
            downloads = json.loads(downloads)
        except Exception:
            downloads = []

    poster = m.get("poster") or ""
    synopsis = m.get("synopsis") or ""
    year = str(m.get("year") or "")
    duration = str(m.get("duration") or "")
    is_series = int(m.get("is_series") or 0)
    tmdb_id = str(m.get("tmdb_id") or "") or None

    has_speedo = any(
        isinstance(e, dict) and (e.get("type") == "speedo" or "speedo" in (e.get("host") or "").lower())
        for e in embeds
    )
    player_kind = "hls" if (has_speedo or not embeds) else "iframe"

    columns = {item[1] for item in conn.execute("PRAGMA table_info(movies)")}
    now_ts = int(time.time())

    # Look up existing YoMovies row strictly within source='yomovies' (exact first, then conservative canonical)
    existing, match_kind = _find_existing_yomovies_row(
        conn, url=url, slug=slug, title=title, year=year, is_series=is_series
    )
    is_new = existing is None

    # Extract genuine print-quality evidence (never treats language 'HINDI' or download server 'HD' as quality)
    incoming_print_q = extract_print_quality(m.get("print_quality"), quality, title)

    if is_new:
        data: Dict[str, Any] = {
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
            "tmdb_id": tmdb_id,
        }
        if "first_added_at" in columns:
            data["first_added_at"] = now_ts
        if "last_checked_at" in columns:
            data["last_checked_at"] = now_ts
        if "last_updated_at" in columns:
            data["last_updated_at"] = now_ts
        if "best_quality" in columns:
            data["best_quality"] = incoming_print_q or quality or None

        filtered = {k: v for k, v in data.items() if k in columns}
        cols = ", ".join(filtered.keys())
        placeholders = ", ".join(f":{k}" for k in filtered.keys())
        conn.execute(f"INSERT INTO movies ({cols}) VALUES ({placeholders})", filtered)
        conn.commit()
        if status_out is not None:
            status_out.update({"outcome": "inserted", "match_kind": None})
        return True

    # Existing YoMovies row matched (either exact or canonical '-2'/'-3' repost)
    movie_id = existing["id"]
    old_print_q = extract_print_quality(
        existing.get("best_quality"),
        existing.get("quality"),
        existing.get("title"),
    )
    is_upg, badge = is_quality_upgrade(old_print_q, incoming_print_q)
    is_down = is_quality_downgrade(old_print_q, incoming_print_q)

    old_embed_codes = _extract_embed_codes(existing.get("embeds"))
    new_embed_codes = _extract_embed_codes(embeds)
    has_incoming_embeds = len(new_embed_codes) > 0
    embeds_changed = has_incoming_embeds and (set(new_embed_codes) != set(old_embed_codes))

    # Merge genres so existing platform/category tags are preserved
    old_genres_raw = existing.get("genres")
    old_genres_list: List[str] = []
    if old_genres_raw:
        try:
            old_genres_list = json.loads(old_genres_raw) if isinstance(old_genres_raw, str) else list(old_genres_raw)
        except Exception:
            old_genres_list = [g.strip() for g in str(old_genres_raw).split(",") if g.strip()]
    merged_genres = list(old_genres_list)
    existing_lower = {str(g).lower() for g in merged_genres}
    for g in genres:
        if str(g).lower() not in existing_lower:
            merged_genres.append(g)
            existing_lower.add(str(g).lower())

    update_fields: Dict[str, Any] = {
        "genres": json.dumps(merged_genres),
    }
    if "last_checked_at" in columns:
        update_fields["last_checked_at"] = now_ts
    # Preserve original first_added_at (backfill only if NULL)
    if "first_added_at" in columns and not existing.get("first_added_at"):
        update_fields["first_added_at"] = int(existing.get("updated_at") or now_ts)

    # Fill missing non-playable metadata safely without overwriting existing trusted metadata
    if tmdb_id and not existing.get("tmdb_id") and "tmdb_id" in columns:
        update_fields["tmdb_id"] = tmdb_id
    if poster and not existing.get("poster"):
        update_fields["poster"] = poster
        if "poster_url" in columns:
            update_fields["poster_url"] = poster
    if synopsis and not existing.get("synopsis"):
        update_fields["synopsis"] = synopsis
    if rating is not None and existing.get("rating") is None and "rating" in columns:
        update_fields["rating"] = rating
    if m.get("imdb") and not existing.get("imdb"):
        update_fields["imdb"] = m.get("imdb")

    outcome = "unchanged"

    if is_down:
        # Case 5: Incoming version is objectively worse than stored print -> NEVER downgrade
        outcome = "downgrade_ignored"
    elif is_upg and badge:
        # Case 3: Genuine verified print-quality upgrade (e.g. CAM/Cinema -> HD/WEB-DL/1080p)
        outcome = "quality_upgraded"
        if has_incoming_embeds:
            update_fields["embeds"] = json.dumps(embeds)
            if "player_kind" in columns:
                update_fields["player_kind"] = player_kind
            if "resolved_at" in columns:
                update_fields["resolved_at"] = None
        if downloads:
            update_fields["downloads"] = json.dumps(downloads)
        if url:
            if "detail_url" in columns:
                update_fields["detail_url"] = url
            # Update url only if it won't collide with another row's UNIQUE url constraint
            if url != existing.get("url"):
                other = conn.execute("SELECT id FROM movies WHERE url=? AND id!=?", (url, movie_id)).fetchone()
                if not other:
                    update_fields["url"] = url
        update_fields["quality"] = incoming_print_q or quality
        if "best_quality" in columns:
            update_fields["best_quality"] = incoming_print_q
        if "last_quality_upgrade_at" in columns:
            update_fields["last_quality_upgrade_at"] = now_ts
        if "latest_quality_transition" in columns:
            update_fields["latest_quality_transition"] = badge
        if "last_updated_at" in columns:
            update_fields["last_updated_at"] = now_ts
        update_fields["updated_at"] = updated_at

        evidence_parts = [f"match={match_kind}"]
        if m.get("article_modified_time"):
            evidence_parts.append(f"article_modified={m['article_modified_time']}")
        if m.get("jsonld_date_modified"):
            evidence_parts.append(f"jsonld_modified={m['jsonld_date_modified']}")
        if embeds_changed:
            evidence_parts.append(f"embeds_changed={len(new_embed_codes)}")
        try:
            conn.execute(
                "INSERT INTO quality_history (movie_id, old_quality, new_quality, transition_badge, upgraded_at, evidence) VALUES (?, ?, ?, ?, ?, ?)",
                (movie_id, old_print_q or existing.get("quality"), incoming_print_q, badge, now_ts, ";".join(evidence_parts)),
            )
        except Exception:
            pass
    elif embeds_changed:
        # Case 4: Quality unclear/equal, but playable embed changed -> replace playable source without fake quality badge
        outcome = "playable_updated"
        update_fields["embeds"] = json.dumps(embeds)
        if downloads:
            update_fields["downloads"] = json.dumps(downloads)
        if "player_kind" in columns:
            update_fields["player_kind"] = player_kind
        if "resolved_at" in columns:
            update_fields["resolved_at"] = None
        if url:
            if "detail_url" in columns:
                update_fields["detail_url"] = url
            if url != existing.get("url"):
                other = conn.execute("SELECT id FROM movies WHERE url=? AND id!=?", (url, movie_id)).fetchone()
                if not other:
                    update_fields["url"] = url
        if incoming_print_q and not old_print_q:
            update_fields["quality"] = incoming_print_q
            if "best_quality" in columns:
                update_fields["best_quality"] = incoming_print_q
        if "last_updated_at" in columns:
            update_fields["last_updated_at"] = now_ts
        update_fields["updated_at"] = updated_at
    else:
        # Case 6: Same version (or empty incoming embeds) -> preserve existing playable data & timestamps
        outcome = "unchanged"

    filtered_upd = {k: v for k, v in update_fields.items() if k in columns}
    if filtered_upd:
        set_clause = ", ".join(f"{k}=:{k}" for k in filtered_upd.keys())
        filtered_upd["_movie_id"] = movie_id
        conn.execute(f"UPDATE movies SET {set_clause} WHERE id=:_movie_id", filtered_upd)

    conn.commit()
    if status_out is not None:
        status_out.update({"outcome": outcome, "match_kind": match_kind, "movie_id": movie_id})
    return False


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
        # Default to active PRMovies & YoMovies mirrors (same catalogue; either healthy mirror succeeds)
        target_bases = []
        for candidate in ["https://prmovies.style", "https://yomovies.irish", *SITE_MIRRORS]:
            c_clean = candidate.strip().rstrip("/")
            if c_clean and c_clean not in target_bases:
                target_bases.append(c_clean)
        target_bases = target_bases[:4]

    http = HttpClient(delay=0.1, cache_dir=".cache")

    print(f"[sync-yomovies] Scraping latest items from mirrors: {', '.join(target_bases)}...", flush=True)

    urls_ordered: List[str] = []
    seen: set = set()
    seen_slugs: set = set()
    forced_genres_by_url: Dict[str, set[str]] = {}
    listing_by_url: Dict[str, Dict[str, Any]] = {}
    page_one_priority_urls: set[str] = set()

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
                        if p == 1 and path in YOMOVIES_PRIORITY_RECHECK_PATHS:
                            page_one_priority_urls.add(u)
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

    rechecks_done = 0
    upgraded = 0
    playable_replaced = 0

    for idx, u in enumerate(urls_ordered):
        try:
            slug = (u.rstrip("/").rsplit("/", 1)[-1] or None) if u else None
            listing_card = listing_by_url.get(u) or {}
            # Check if any db already has this YoMovies movie (exact or conservative canonical match)
            existing_row = None
            match_kind = None
            for conn in conns:
                found_row, found_kind = _find_existing_yomovies_row(
                    conn,
                    url=u,
                    slug=slug,
                    title=listing_card.get("title"),
                    year=listing_card.get("year"),
                    is_series=int(listing_card.get("is_series") or 0),
                )
                if found_row:
                    existing_row = found_row
                    match_kind = found_kind
                    break

            should_fetch_detail = False
            if not existing_row:
                should_fetch_detail = True
            elif rechecks_done < YOMOVIES_MAX_RECHECKS_PER_RUN:
                should_fetch_detail = _should_recheck_yomovies_detail(
                    existing_row,
                    listing_card,
                    is_page_one_priority=(u in page_one_priority_urls),
                    is_canonical_repost=(match_kind == "canonical"),
                    now_ts=base_time,
                )

            info = None
            if should_fetch_detail:
                if existing_row:
                    rechecks_done += 1
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
            else:
                # Fast path: existing YoMovies row recently checked & no upgrade signal -> skip detail fetch
                info = dict(existing_row)
                for k in ("genres", "actors", "director", "country", "embeds", "downloads"):
                    if isinstance(info.get(k), str):
                        try:
                            info[k] = json.loads(info[k])
                        except Exception:
                            pass

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
            last_status: Dict[str, Any] = {}
            for conn in conns:
                was_new = upsert_yomovies_item(conn, info, recency_timestamp, status_out=last_status)
                if was_new:
                    is_new_overall = True

            embs_count = len(info.get("embeds") or [])
            outcome = last_status.get("outcome")
            if is_new_overall:
                added += 1
                print(f"[sync-yomovies] + ADDED: {info['title']} ({info.get('year')}) [{embs_count} embeds]", flush=True)
            else:
                updated += 1
                if outcome == "quality_upgraded":
                    upgraded += 1
                    print(f"[sync-yomovies] ^ UPGRADED: {info['title']} ({info.get('year')})", flush=True)
                elif outcome == "playable_updated":
                    playable_replaced += 1
                    print(f"[sync-yomovies] ~ REPLACED EMBED: {info['title']} ({info.get('year')})", flush=True)
                elif idx < 10:
                    print(f"[sync-yomovies] ~ REFRESHED: {info['title']} ({info.get('year')})", flush=True)

        except Exception as e:
            print(f"[sync-yomovies] Error ingesting {u}: {e}", flush=True)

    for conn in conns:
        conn.close()
    http.close()

    print(
        f"[sync-yomovies] Finished: {added} new titles added, {updated} refreshed "
        f"({upgraded} quality upgrades, {playable_replaced} embed replacements, {rechecks_done} detail rechecks).",
        flush=True,
    )
    return {
        "added": added,
        "updated": updated,
        "upgraded": upgraded,
        "playable_replaced": playable_replaced,
        "rechecks": rechecks_done,
        "total": len(urls_ordered),
    }


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


def run_full_sync(*, notifier: Any = None) -> Dict[str, Any]:
    """Run full catalog sync across all configured sources and emit one best-effort SyncRunReport."""
    global _LAST_SYNC_META
    _LAST_SYNC_META["status"] = "running"
    start_time = time.time()
    base_time = int(start_time)

    print("=" * 60)
    print("[SYNC] CineMyMovies Automated Catalog Sync Started")
    print("=" * 60)

    from app.notifications import (
        TelegramNotifier,
        build_sync_run_report,
        source_report_from_dict,
    )

    source_reports = []

    def _run_source(label: str, fn) -> Dict[str, Any]:
        s_start = int(time.time())
        try:
            res_dict = fn() or {}
            source_reports.append(
                source_report_from_dict(label, res_dict, started_at=s_start, finished_at=int(time.time()))
            )
            return res_dict
        except Exception as exc:
            logger.exception("[SYNC] Source %s failed: %s", label, exc)
            source_reports.append(
                source_report_from_dict(label, None, started_at=s_start, finished_at=int(time.time()), exception=exc)
            )
            return {"status": "failed", "added": 0, "updated": 0, "skipped": 0, "total": 0, "errors": 1}

    from app.adapters.registry import ADAPTERS

    _SOURCE_LABELS = {
        "yomovies": "YoMovies",
        "moviesdrive": "MoviesDrive",
        "ask4movie": "Ask4Movies",
        "movies7": "Movies7",
        "dooflix": "DuoFlix",
        "flixmovie": "FlixMovie",
    }
    _SYNC_HANDLERS = {
        "yomovies": lambda: sync_yomovies(base_time),
        "moviesdrive": lambda: sync_moviesdrive(base_time, pages_per_mirror=3),
        "ask4movie": lambda: sync_ask4movie(base_time),
        "movies7": lambda: sync_movies7(pages_per_category=5),
        "dooflix": lambda: sync_dooflix(base_time),
        "flixmovie": lambda: sync_flixmovie(base_time, pages_per_category=2),
    }

    # Drive execution & reporting dynamically from every registered adapter in ADAPTERS
    results_by_key: Dict[str, Dict[str, Any]] = {}
    for key in ADAPTERS.keys():
        label = _SOURCE_LABELS.get(key, key.title())
        handler = _SYNC_HANDLERS.get(key)
        if handler is None:
            source_reports.append(
                source_report_from_dict(
                    label,
                    {"status": "warning", "added": 0, "updated": 0, "skipped": 0, "total": 0, "warnings": [f"{label} has no sync handler configured"]},
                )
            )
            results_by_key[key] = {"added": 0, "updated": 0, "skipped": 0, "total": 0}
            continue
        results_by_key[key] = _run_source(label, handler)

    # Read final catalogue total (read-only) for the Telegram summary
    catalogue_total: Optional[int] = None
    try:
        db_paths = get_target_db_paths()
        if db_paths and os.path.exists(db_paths[0]):
            with sqlite3.connect(db_paths[0], timeout=5) as _c:
                catalogue_total = int(_c.execute("SELECT COUNT(*) FROM movies").fetchone()[0])
    except Exception:
        pass

    finished_ts = int(time.time())
    duration = round(time.time() - start_time, 2)
    run_report = build_sync_run_report(
        source_reports,
        started_at=base_time,
        finished_at=finished_ts,
        catalogue_total=catalogue_total,
    )

    summary = {
        "status": "success",
        "overall_status": run_report.overall_status.value,
        "duration_seconds": duration,
        "timestamp": base_time,
        **results_by_key,
        "total_added": sum(int(r.get("added", 0) or 0) for r in results_by_key.values()),
        "total_refreshed": sum(int(r.get("updated", 0) or 0) for r in results_by_key.values()),
        "total_skipped": sum(int(r.get("skipped", 0) or 0) for r in results_by_key.values()),
        "catalogue_total": catalogue_total,
        "report": run_report,
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

    # Best-effort single final notifications (Telegram & ntfy; never fail the sync)
    try:
        active_notifier = notifier if notifier is not None else TelegramNotifier.from_env()
        notify_res = active_notifier.send_sync_report(run_report)
        if notify_res.sent:
            print(f"[SYNC] Telegram notification sent ({notify_res.messages_sent} message(s)).", flush=True)
        elif not notify_res.skipped:
            print(f"[SYNC] Note: {notify_res.reason}", flush=True)
    except Exception as exc:
        print(f"[SYNC] Note: Telegram notification skipped due to error: {type(exc).__name__}", flush=True)

    try:
        from app.notifications import NtfyNotifier
        ntfy_res = NtfyNotifier.from_env().send_sync_report(run_report)
        if ntfy_res.sent:
            print(f"[SYNC] ntfy notification sent ({ntfy_res.messages_sent} message(s)).", flush=True)
        elif not ntfy_res.skipped:
            print(f"[SYNC] Note: {ntfy_res.reason}", flush=True)
    except Exception as exc:
        print(f"[SYNC] Note: ntfy notification skipped due to error: {type(exc).__name__}", flush=True)

    return summary


def get_sync_status() -> Dict[str, Any]:
    return dict(_LAST_SYNC_META)


if __name__ == "__main__":
    run_full_sync()
