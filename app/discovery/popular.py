"""Evergreen Picks discovery engine for CINEMY.

Completely distinct from Trending Now:
- Measures established, year-independent desirability using proven catalogue signals
  (rating quality with 1-vote noise protection, cast/director/genre/synopsis metadata richness,
  primary/multi-source availability, and print quality).
- Release year is only a tiny tie-breaker (<= 1.5 pts) so iconic classics naturally outrank
  mediocre recent releases.
- Explicitly excludes animated titles using catalogue metadata (genres / media_type).
- Balances CINEMY's natural catalogue diversity across English/Hollywood movies & series,
  Hindi/Indian movies & series, Punjabi titles, and other strong Indian regional titles
  without forcing weak candidates or hard-coding any title whitelist.
- Supports canonical cross-row exclusions (`exclude_ids`, `exclude_titles`) to achieve zero
  overlap against Trending Now whenever sufficient candidates exist.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import defaultdict
from typing import Any, Optional

from ..api.routes_catalog import (
    ADULT_EXCLUSION_SQL,
    _format_row,
    _get_fallback_posters,
    _normalized_title,
    _source_priority,
    get_canonical_source_count,
    get_db_connection,
    is_movie_available_on_primary_sources,
)
from .trending import (
    ANIMATION_EXCLUSION_SQL,
    _is_animated_row,
    _parse_rating,
    _parse_year,
)

EVERGREEN_CACHE_TTL = 120.0
EVERGREEN_CACHE_MAX = 64
DEFAULT_EVERGREEN_LIMIT = 50
MAX_EVERGREEN_LIMIT = 50

# Backwards-compatible aliases
POPULAR_CACHE_TTL = EVERGREEN_CACHE_TTL
POPULAR_CACHE_MAX = EVERGREEN_CACHE_MAX
DEFAULT_POPULAR_LIMIT = DEFAULT_EVERGREEN_LIMIT
MAX_POPULAR_LIMIT = MAX_EVERGREEN_LIMIT

# Soft target proportions for 50 Evergreen Picks (Punjabi excluded per user preference; includes classic comedy diversity)
EVERGREEN_BUCKET_WEIGHTS: dict[str, float] = {
    "english_movie": 9.0 / 50.0,
    "english_comedy": 4.0 / 50.0,
    "english_series": 19.0 / 50.0,
    "hindi_movie": 9.0 / 50.0,
    "hindi_series": 7.0 / 50.0,
    "other_indian": 2.0 / 50.0,
}
MIN_BUCKET_QUALITY_SCORE = 42.0

PUNJABI_EXCLUSION_SQL = (
    "LOWER(COALESCE(genres, '')) NOT LIKE '%punjabi%' "
    "AND LOWER(COALESCE(language, '')) NOT LIKE '%punjabi%' "
    "AND LOWER(COALESCE(quality, '')) NOT LIKE '%punjabi%' "
    "AND LOWER(COALESCE(title, '')) NOT LIKE '%punjabi%'"
)


def _is_punjabi_row(row: dict[str, Any]) -> bool:
    blob = " ".join(
        str(row.get(k) or "").lower()
        for k in ("genres", "language", "quality", "title")
    )
    return "punjabi" in blob

_evergreen_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}
_evergreen_cache_lock = threading.Lock()


def invalidate_evergreen_cache() -> None:
    with _evergreen_cache_lock:
        _evergreen_cache.clear()


invalidate_popular_cache = invalidate_evergreen_cache


def _parse_json_list(val: Any) -> list[str]:
    if not val:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if x and str(x).strip()]
    if isinstance(val, str):
        s = val.strip()
        if not s or s == "[]":
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if x and str(x).strip()]
            except Exception:
                pass
        return [p.strip() for p in re.split(r"[,|]+", s) if p.strip()]
    return []


def _classify_evergreen_bucket(row: dict[str, Any]) -> str:
    """
    Classify a catalogue row into a broad language/media bucket using real catalogue metadata
    (language, country, genres, quality, title, is_series).
    """
    is_series = bool(row.get("is_series"))
    genres = " ".join(_parse_json_list(row.get("genres"))).lower()
    country = " ".join(_parse_json_list(row.get("country"))).lower()
    language = str(row.get("language") or "").lower()
    quality = str(row.get("quality") or "").lower()
    title = str(row.get("title") or "").lower()

    meta_blob = f"{genres} {language} {quality}"

    # 1. Punjabi movies & series
    if "punjabi" in meta_blob or "punjabi" in title:
        return "punjabi"

    # 2. Other strong Indian regional cinema (Tamil, Telugu, Malayalam, Kannada, Marathi, Bengali, etc.)
    regional_tokens = ("tamil", "telugu", "malayalam", "kannada", "marathi", "bengali", "gujarati", "south indian", "tollywood", "kollywood")
    if any(tok in meta_blob for tok in regional_tokens) or any(tok in title for tok in ("tamil", "telugu", "malayalam", "kannada")):
        return "other_indian"

    # 3. Distinguish Hollywood/English dubbed into Hindi from native Indian/Bollywood content
    is_western_country = any(
        c in country
        for c in ("united states", "usa", "united kingdom", "uk", "canada", "australia", "new zealand", "ireland")
    )
    is_hollywood_tag = "hollywood" in genres
    is_indian = (
        ("india" in country and not is_western_country)
        or "bollywood" in genres
        or "indian" in genres
        or (language == "hindi" and not is_western_country and not is_hollywood_tag)
    )

    if is_indian:
        return "hindi_series" if is_series else "hindi_movie"

    if is_series:
        return "english_series"

    # Dedicated bucket for established pure Hollywood comedy classics (excludes sci-fi/adventure/fantasy)
    year = _parse_year(row)
    if (
        1990 <= year <= 2018
        and "comedy" in genres
        and not any(g in genres for g in ("drama", "crime", "action", "thriller", "sci-fi", "fantasy", "adventure"))
    ):
        return "english_comedy"

    return "english_movie"


def _evergreen_popular_score(row: dict[str, Any], distinct_sources: int) -> float:
    """
    Deterministic evergreen popularity score (year-independent):
      1. Rating quality (up to 45.0 pts; ratings > 9.5 are discounted as likely 1-vote noise)
      2. Metadata confidence / richness (up to 22.0 pts; does NOT penalize TV series for missing film director)
      3. Established cross-source availability (up to 16.0 pts: equal primary source weight for yomovies/dooflix
         + full-catalogue multi-source presence across yomovies/dooflix/ask4movie/movies7)
      4. Print quality availability (up to 8.0 pts)
      5. Minor recency tie-breaker ONLY (up to 1.5 pts max)
      6. Small poster-reliability nudge (-4.0 pts) ONLY if sole poster is a legacy Amazon URL with no DB mirror
    """
    rating = _parse_rating(row)
    if rating <= 0.0:
        rating_pts = 8.0
    elif rating > 9.5:
        # 9.6-10.0 in scraped TMDB/IMDb feeds is frequently 1-vote noise; cap below proven 9.0-9.5 classics
        rating_pts = 36.0
    else:
        # Primary weight on proven 6.5 -> 9.5 ratings (up to 55.0 pts)
        rating_pts = min(55.0, max(10.0, (rating / 9.5) * 55.0))

    # Metadata confidence / canonical completeness (up to 22.0 pts)
    actors = _parse_json_list(row.get("actors"))
    directors = _parse_json_list(row.get("director"))
    genres = _parse_json_list(row.get("genres"))
    synopsis = str(row.get("synopsis") or "").strip()
    is_series = bool(row.get("is_series"))

    meta_pts = 0.0
    if is_series:
        # TV series on dooflix/TMDB rarely populate `director`; allocate full 22 pts across cast/genres/synopsis
        if len(actors) >= 3:
            meta_pts += 9.0
        elif len(actors) >= 1:
            meta_pts += 5.0
        if len(genres) >= 2:
            meta_pts += 6.0
        elif len(genres) >= 1:
            meta_pts += 3.0
        if len(synopsis) >= 40:
            meta_pts += 7.0
        elif len(synopsis) >= 15:
            meta_pts += 4.0
    else:
        if len(actors) >= 5:
            meta_pts += 8.0
        elif len(actors) >= 2:
            meta_pts += 5.0
        elif len(actors) >= 1:
            meta_pts += 2.0

        if len(directors) >= 1:
            meta_pts += 5.0

        if len(genres) >= 2:
            meta_pts += 5.0
        elif len(genres) >= 1:
            meta_pts += 2.0

        if len(synopsis) >= 40:
            meta_pts += 4.0
        elif len(synopsis) >= 15:
            meta_pts += 2.0

    # Established cross-source availability (up to 16.0 pts; yomovies & dooflix treated equally as primary sources)
    src = str(row.get("source") or "").lower()
    if src in ("yomovies", "dooflix"):
        src_pts = 6.0
    elif src == "ask4movie":
        src_pts = 4.0
    else:
        src_pts = 2.0
    # Cross-source availability (capped at +2.0 pts so rating quality stays primary over scraper count)
    mirror_pts = min(2.0, max(0, distinct_sources - 1) * 0.5)

    # Quality availability (up to 8.0 pts)
    q = f"{row.get('best_quality') or ''} {row.get('quality') or ''}".lower()
    if "4k" in q or "2160" in q:
        qual_pts = 8.0
    elif "1080" in q or "bluray" in q or "bdrip" in q or "web-dl" in q or "fhd" in q:
        qual_pts = 6.0
    elif "720" in q or "hd" in q:
        qual_pts = 4.0
    elif "hindi" in q or "punjabi" in q:
        qual_pts = 3.0
    else:
        qual_pts = 1.0

    # Evergreen longevity signal: established titles (<= 2023) get a small bonus over brand-new 2025-2026 releases
    year = _parse_year(row)
    if 1950 <= year <= 2023:
        tie_pts = 3.0
    elif year == 2024:
        tie_pts = 1.0
    else:
        tie_pts = 0.0

    # Small poster-reliability nudge for legacy Amazon URLs lacking any DB mirror fallback
    poster_val = str(row.get("poster") or row.get("poster_url") or "").lower()
    poster_nudge = 0.0
    if "m.media-amazon.com" in poster_val and "xkeyxkfqcgde" in poster_val:
        if not _get_fallback_posters(row.get("title"), row.get("is_series"), poster_val):
            poster_nudge = -4.0

    return round(rating_pts + meta_pts + src_pts + mirror_pts + qual_pts + tie_pts + poster_nudge, 4)


def _select_balanced_evergreen(
    ordered_candidates: list[tuple[float, int, dict[str, Any]]],
    limit: int,
) -> list[dict[str, Any]]:
    """
    Select up to `limit` evergreen candidates respecting soft language/category targets
    while never forcing weak candidates (score < MIN_BUCKET_QUALITY_SCORE) into a slot.
    Interleaves selected buckets smoothly by score so the row feels naturally varied.
    """
    if limit <= 0 or not ordered_candidates:
        return []

    bucket_pools: dict[str, list[tuple[float, int, dict[str, Any]]]] = defaultdict(list)
    for entry in ordered_candidates:
        bucket = _classify_evergreen_bucket(entry[2])
        bucket_pools[bucket].append(entry)

    # Compute soft target counts scaled to `limit`
    targets: dict[str, int] = {}
    for bucket, weight in EVERGREEN_BUCKET_WEIGHTS.items():
        targets[bucket] = max(1, int(round(weight * limit))) if limit >= 10 else max(0, int(round(weight * limit)))

    chosen: list[tuple[float, int, dict[str, Any]]] = []
    chosen_ids: set[int] = set()

    # Pass 1: Fill each bucket up to its soft target with strong candidates only
    for bucket, target_count in targets.items():
        if target_count <= 0:
            continue
        taken = 0
        for entry in bucket_pools.get(bucket, []):
            score, _, row = entry
            if score < MIN_BUCKET_QUALITY_SCORE:
                break
            rid = int(row["id"])
            if rid in chosen_ids:
                continue
            chosen.append(entry)
            chosen_ids.add(rid)
            taken += 1
            if taken >= target_count or len(chosen) >= limit:
                break

    # Pass 2: Fill any remaining slots with the strongest eligible candidates globally
    if len(chosen) < limit:
        for entry in ordered_candidates:
            rid = int(entry[2]["id"])
            if rid in chosen_ids:
                continue
            chosen.append(entry)
            chosen_ids.add(rid)
            if len(chosen) >= limit:
                break

    # Sort final selection by evergreen score descending (tie-break by source priority & id)
    chosen.sort(key=lambda e: (-e[0], e[1], -(int(e[2].get("id") or 0))))
    return [_format_row(row) for _, _, row in chosen[:limit]]


def get_evergreen_titles(
    limit: int = DEFAULT_EVERGREEN_LIMIT,
    exclude_ids: Optional[list[int]] = None,
    exclude_titles: Optional[set[str]] = None,
) -> dict[str, Any]:
    """
    Return up to `limit` (default 50, max 50) evergreen all-time popular titles,
    excluding animated titles and canonical Trending overlaps, balanced across
    CINEMY's Hindi, English/Hollywood, Punjabi, and Indian regional catalogue.
    """
    limit = min(MAX_EVERGREEN_LIMIT, max(1, int(limit)))
    clean_ex_ids = sorted({int(x) for x in (exclude_ids or []) if isinstance(x, int) and x > 0})[:100]
    clean_ex_titles = sorted({t for t in (exclude_titles or set()) if t})[:100]

    cache_key = (limit, tuple(clean_ex_ids), tuple(clean_ex_titles))
    now_mono = time.monotonic()
    with _evergreen_cache_lock:
        cached = _evergreen_cache.get(cache_key)
        if cached and (now_mono - cached[0] < EVERGREEN_CACHE_TTL):
            return cached[1]

    ex_id_set = set(clean_ex_ids)
    ex_title_set = set(clean_ex_titles)

    with get_db_connection() as conn:
        # Resolve normalized titles of excluded IDs so mirror copies of Trending titles are also excluded
        if clean_ex_ids:
            ph = ",".join("?" for _ in clean_ex_ids)
            for r in conn.execute(f"SELECT title FROM movies WHERE id IN ({ph})", clean_ex_ids).fetchall():
                nt = _normalized_title(r["title"])
                if nt:
                    ex_title_set.add(nt)

        base_where = f"""
            title IS NOT NULL AND title != ''
            AND (COALESCE(poster, poster_url, '') != '' AND poster NOT LIKE '%logo.png%')
            AND ({ADULT_EXCLUSION_SQL})
            AND ({ANIMATION_EXCLUSION_SQL})
            AND ({PUNJABI_EXCLUSION_SQL})
        """
        order_clause = """
            ORDER BY
                CASE
                    WHEN COALESCE(rating, 0) BETWEEN 7.0 AND 9.5
                         AND (
                             length(COALESCE(actors, '')) > 5
                             OR length(COALESCE(synopsis, '')) > 20
                         ) THEN 0
                    WHEN COALESCE(rating, 0) BETWEEN 6.8 AND 9.5 THEN 1
                    ELSE 2
                END ASC,
                COALESCE(rating, CAST(REPLACE(REPLACE(COALESCE(imdb, ''), 'IMDb: ', ''), '★ ', '') AS REAL), 0) DESC,
                length(COALESCE(actors, '')) DESC,
                id DESC
        """

        # Bounded Query 1: Broad high-rated evergreen pool across all sources (<= 1200 rows)
        primary_rows = conn.execute(
            f"SELECT * FROM movies WHERE {base_where} {order_clause} LIMIT 1200"
        ).fetchall()

        # Bounded Query 2: Dedicated Indian / Bollywood / Regional pool (<= 300 rows, Punjabi excluded)
        regional_rows = conn.execute(
            f"""
            SELECT * FROM movies
            WHERE {base_where}
              AND (
                  LOWER(COALESCE(genres, '')) LIKE '%bollywood%'
                  OR LOWER(COALESCE(country, '')) LIKE '%india%'
                  OR LOWER(COALESCE(genres, '')) LIKE '%tamil%'
                  OR LOWER(COALESCE(genres, '')) LIKE '%telugu%'
                  OR LOWER(COALESCE(genres, '')) LIKE '%malayalam%'
              )
            {order_clause}
            LIMIT 300
            """
        ).fetchall()

        # Bounded Query 3: Classic pure Hollywood comedy pool (<= 30 rows) so evergreen comedies
        # (rating 7.5-8.0) are evaluated alongside 8.5+ dramas without scanning the full table
        comedy_rows = conn.execute(
            f"""
            SELECT * FROM movies
            WHERE {base_where}
              AND is_series = 0
              AND CAST(COALESCE(NULLIF(year, ''), '0') AS INT) BETWEEN 1990 AND 2018
              AND COALESCE(rating, 0) >= 7.5
              AND LOWER(COALESCE(genres, '')) LIKE '%comedy%'
              AND LOWER(COALESCE(genres, '')) NOT LIKE '%drama%'
              AND LOWER(COALESCE(genres, '')) NOT LIKE '%crime%'
              AND LOWER(COALESCE(genres, '')) NOT LIKE '%action%'
              AND LOWER(COALESCE(genres, '')) NOT LIKE '%thriller%'
              AND LOWER(COALESCE(genres, '')) NOT LIKE '%sci-fi%'
              AND LOWER(COALESCE(genres, '')) NOT LIKE '%fantasy%'
              AND LOWER(COALESCE(genres, '')) NOT LIKE '%adventure%'
              AND (
                  LOWER(COALESCE(country, '')) LIKE '%united states%'
                  OR LOWER(COALESCE(country, '')) LIKE '%usa%'
                  OR LOWER(COALESCE(country, '')) LIKE '%united kingdom%'
                  OR LOWER(COALESCE(genres, '')) LIKE '%hollywood%'
              )
            ORDER BY COALESCE(rating, 0) DESC, id DESC
            LIMIT 30
            """
        ).fetchall()

    # Merge by raw row ID to avoid double-counting rows returned by bounded queries
    merged_by_id: dict[int, dict[str, Any]] = {}
    for r in primary_rows:
        d = dict(r)
        merged_by_id[int(d["id"])] = d
    for r in regional_rows:
        d = dict(r)
        merged_by_id.setdefault(int(d["id"]), d)
    for r in comedy_rows:
        d = dict(r)
        merged_by_id.setdefault(int(d["id"]), d)

    raw_dicts = [d for d in merged_by_id.values() if not _is_animated_row(d) and not _is_punjabi_row(d)]

    # Deduplicate by canonical (normalized_title, is_series) so multi-season shows & mirrors appear once
    dedup_primary: dict[tuple[str, int], tuple[float, int, dict[str, Any]]] = {}
    dedup_overflow: dict[tuple[str, int], tuple[float, int, dict[str, Any]]] = {}

    for d in raw_dicts:
        if d.get("source") == "movies7" and is_movie_available_on_primary_sources(d.get("title"), d.get("year")):
            continue
        nt = _normalized_title(d.get("title")) or f"id:{d.get('id')}"
        is_s = 1 if d.get("is_series") else 0
        key = (nt, is_s)
        distinct_sources = get_canonical_source_count(d.get("title"), is_s)
        score = _evergreen_popular_score(d, distinct_sources)
        prio = _source_priority(d.get("source"))

        is_excluded = (int(d["id"]) in ex_id_set) or (nt in ex_title_set)
        target_map = dedup_overflow if is_excluded else dedup_primary

        existing = target_map.get(key)
        if existing is None:
            target_map[key] = (score, prio, d)
        else:
            prev_score, prev_prio, _ = existing
            if score > prev_score + 1.5 or (abs(score - prev_score) <= 1.5 and prio < prev_prio):
                target_map[key] = (max(score, prev_score), min(prio, prev_prio), d)

    ordered_primary = sorted(
        dedup_primary.values(),
        key=lambda e: (-e[0], e[1], -(int(e[2].get("id") or 0))),
    )
    items = _select_balanced_evergreen(ordered_primary, limit=limit)

    # Only fall back to excluded items if the catalogue is too small to fill `limit`
    if len(items) < limit and dedup_overflow:
        used_keys = {(_normalized_title(m.get("title")), 1 if m.get("is_series") else 0) for m in items}
        ordered_overflow = sorted(
            dedup_overflow.values(),
            key=lambda e: (-e[0], e[1], -(int(e[2].get("id") or 0))),
        )
        for _, _, row in ordered_overflow:
            k = (_normalized_title(row.get("title")), 1 if row.get("is_series") else 0)
            if k not in used_keys:
                items.append(_format_row(row))
                used_keys.add(k)
                if len(items) >= limit:
                    break

    result = {
        "items": items[:limit],
        "total": len(items[:limit]),
        "mode": "evergreen_picks",
    }

    with _evergreen_cache_lock:
        if len(_evergreen_cache) >= EVERGREEN_CACHE_MAX:
            oldest = min(_evergreen_cache, key=lambda k: _evergreen_cache[k][0])
            _evergreen_cache.pop(oldest, None)
        _evergreen_cache[cache_key] = (now_mono, result)

    return result


# Clean aliases
get_evergreen = get_evergreen_titles
get_popular_titles = get_evergreen_titles
