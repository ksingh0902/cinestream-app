"""Trending Now discovery engine for CINEMY.

Supports:
1. Real aggregate viewer activity (when a `viewer_activity` table exists and has recent events),
   weighting unique viewers, capped per-viewer plays, watch completion quality, and time-decay recency.
2. Deterministic `fallback_trending` ranking using verified catalogue signals (rating, recent release,
   quality tier, quality upgrades, and multi-source availability) when server-side activity data is
   absent or insufficient.
"""
from __future__ import annotations

import math
import re
import sqlite3
import threading
import time
from collections import defaultdict
from typing import Any

from ..api.routes_catalog import (
    ADULT_EXCLUSION_SQL,
    _format_row,
    _normalized_title,
    _source_priority,
    get_db_connection,
    is_movie_available_on_primary_sources,
)

TRENDING_CACHE_TTL = 120.0
TRENDING_CACHE_MAX = 32
DEFAULT_TRENDING_LIMIT = 50
MAX_TRENDING_LIMIT = 50

ANIMATION_EXCLUSION_SQL = (
    "LOWER(COALESCE(genres, '')) NOT LIKE '%animation%' "
    "AND LOWER(COALESCE(genres, '')) NOT LIKE '%animated%' "
    "AND LOWER(COALESCE(genres, '')) NOT LIKE '%anime%' "
    "AND LOWER(COALESCE(genres, '')) NOT LIKE '%cartoon%'"
)


def _is_animated_row(row: dict[str, Any]) -> bool:
    """Detect animated titles using catalogue metadata (genres / media_type)."""
    genres_raw = str(row.get("genres") or "").lower()
    media_type = str(row.get("media_type") or "").lower()
    combined = f"{genres_raw} {media_type}"
    return any(tok in combined for tok in ("animation", "animated", "anime", "cartoon"))

_trending_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}
_trending_cache_lock = threading.Lock()


def invalidate_trending_cache() -> None:
    with _trending_cache_lock:
        _trending_cache.clear()


def _parse_rating(row: dict[str, Any]) -> float:
    try:
        if row.get("rating") is not None:
            val = float(row["rating"])
            if 0.0 < val <= 10.0:
                return val
        imdb_str = str(row.get("imdb") or "")
        m = re.search(r"(\d+(?:\.\d+)?)", imdb_str)
        if m:
            val = float(m.group(1))
            if 0.0 < val <= 10.0:
                return val
    except Exception:
        pass
    return 0.0


def _parse_year(row: dict[str, Any]) -> int:
    try:
        y = str(row.get("year") or "").strip()
        if y.isdigit() and len(y) == 4:
            return int(y)
    except Exception:
        pass
    return 0


def _quality_score(row: dict[str, Any]) -> float:
    q = f"{row.get('best_quality') or ''} {row.get('quality') or ''}".lower()
    if "4k" in q or "2160" in q:
        return 12.0
    if "bluray" in q or "bdrip" in q or "1080" in q or "fhd" in q or "web-dl" in q:
        return 9.0
    if "720" in q or "hd" in q:
        return 6.0
    if "hindi" in q or "punjabi" in q:
        return 4.0
    return 0.0


def _has_activity_table(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='viewer_activity'"
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def _score_from_activity(conn: sqlite3.Connection, window_days: int = 14) -> dict[int, float]:
    """
    Aggregate real viewer activity events into a deterministic Trending score per movie_id.
    Prevents a single viewer from dominating by weighting unique viewers strongly and capping
    per-viewer play counts, while rewarding watch completion and recent momentum.
    """
    now = int(time.time())
    cutoff = now - (max(1, window_days) * 86400)
    rows = conn.execute(
        """
        SELECT viewer_id, movie_id, watched_seconds, duration_seconds, created_at
        FROM viewer_activity
        WHERE created_at >= ?
        ORDER BY created_at DESC
        LIMIT 10000
        """,
        (cutoff,),
    ).fetchall()

    if not rows:
        return {}

    # Track per-(movie, viewer) stats so one user looping a title has bounded impact
    per_movie_viewers: dict[int, dict[str, dict[str, float]]] = defaultdict(dict)
    for r in rows:
        mid = int(r["movie_id"])
        vid = str(r["viewer_id"] or "")
        if not vid:
            continue
        age_days = max(0.0, (now - int(r["created_at"] or now)) / 86400.0)
        # Exponential-style time decay: today=1.0, 3 days ago=0.5, 9 days ago=0.25
        recency_weight = 1.0 / (1.0 + age_days / 3.0)
        watched = float(r["watched_seconds"] or 0.0)
        duration = float(r["duration_seconds"] or 0.0)
        completion = min(1.0, watched / duration) if duration > 0 else (0.5 if watched >= 60 else 0.25)

        entry = per_movie_viewers[mid].get(vid)
        if entry is None:
            per_movie_viewers[mid][vid] = {
                "plays": 1.0,
                "best_recency": recency_weight,
                "best_completion": completion,
            }
        else:
            entry["plays"] = min(3.0, entry["plays"] + 1.0)
            entry["best_recency"] = max(entry["best_recency"], recency_weight)
            entry["best_completion"] = max(entry["best_completion"], completion)

    scores: dict[int, float] = {}
    for mid, viewer_map in per_movie_viewers.items():
        unique_viewers = len(viewer_map)
        total_score = 0.0
        for stats in viewer_map.values():
            # Unique viewer base (4.0) + capped repeat play signal + completion quality, scaled by recency
            viewer_contrib = (
                4.0
                + math.log1p(stats["plays"]) * 1.5
                + stats["best_completion"] * 2.5
            ) * stats["best_recency"]
            total_score += viewer_contrib
        # Bonus for breadth of distinct viewers
        total_score += math.log1p(unique_viewers) * 2.0
        scores[mid] = round(total_score, 4)
    return scores


def _fallback_trending_score(row: dict[str, Any], mirror_count: int, now_ts: int) -> float:
    """
    Deterministic fallback trending score using verified catalogue signals.
    Distinct from Recently Added: prioritizes critically acclaimed, high-quality,
    multi-source recent releases rather than raw crawl insertion order.
    """
    rating = _parse_rating(row)
    year = _parse_year(row)
    q_score = _quality_score(row)

    # Strong rating signal (up to 40 pts)
    rating_pts = (rating / 10.0) * 40.0 if rating > 0 else 12.0

    # Release recency momentum (up to 24 pts; prefers 2024-2026)
    if year >= 2026:
        year_pts = 24.0
    elif year == 2025:
        year_pts = 20.0
    elif year == 2024:
        year_pts = 15.0
    elif year == 2023:
        year_pts = 10.0
    elif year >= 2020:
        year_pts = 6.0
    else:
        year_pts = 2.0

    # Recent verified quality upgrade boost (up to 8 pts)
    upgrade_pts = 0.0
    upg_at = row.get("last_quality_upgrade_at")
    if upg_at and (now_ts - int(upg_at)) <= 90 * 86400:
        upgrade_pts = 8.0

    # Multi-source catalogue availability boost (capped at +6 pts so duplicate mirrors never dominate)
    mirror_pts = min(6.0, max(0, mirror_count - 1) * 3.0)

    # Slight preference for primary streaming sources
    src_pts = max(0.0, 3.0 - _source_priority(row.get("source")) * 0.8)

    return round(rating_pts + year_pts + q_score + upgrade_pts + mirror_pts + src_pts, 4)


def _deduplicate_and_rank(
    scored_rows: list[tuple[float, dict[str, Any]]],
    limit: int,
) -> list[dict[str, Any]]:
    """
    Deduplicate across yomovies/dooflix/ask4movie/movies7 by canonical normalized (title, year, is_series).
    Prefers higher score, breaking close ties by established CINEMY source priority.
    Excludes animated titles via catalogue metadata.
    """
    dedup: dict[tuple[str, str, int], tuple[float, int, dict[str, Any]]] = {}
    for score, row in scored_rows:
        if _is_animated_row(row):
            continue
        if row.get("source") == "movies7" and is_movie_available_on_primary_sources(row.get("title"), row.get("year")):
            continue
        nt = _normalized_title(row.get("title")) or f"id:{row.get('id')}"
        yr = str(row.get("year") or "").strip()
        is_s = 1 if row.get("is_series") else 0
        key = (nt, yr, is_s)
        prio = _source_priority(row.get("source"))

        existing = dedup.get(key)
        if existing is None:
            dedup[key] = (score, prio, row)
        else:
            prev_score, prev_prio, _ = existing
            if score > prev_score + 1.5 or (abs(score - prev_score) <= 1.5 and prio < prev_prio):
                dedup[key] = (max(score, prev_score), min(prio, prev_prio), row)

    ordered = sorted(
        dedup.values(),
        key=lambda e: (-e[0], e[1], -(int(e[2].get("id") or 0))),
    )
    return [_format_row(row) for _, _, row in ordered[:limit]]


def get_trending_titles(limit: int = DEFAULT_TRENDING_LIMIT, window_days: int = 14) -> dict[str, Any]:
    """Return bounded Trending Now items (8-12 default, max 20), cached globally for 120s."""
    limit = min(MAX_TRENDING_LIMIT, max(1, int(limit)))
    window_days = min(90, max(1, int(window_days)))
    cache_key = (limit, window_days)

    now_mono = time.monotonic()
    with _trending_cache_lock:
        cached = _trending_cache.get(cache_key)
        if cached and (now_mono - cached[0] < TRENDING_CACHE_TTL):
            return cached[1]

    now_ts = int(time.time())
    mode = "fallback_trending"
    is_fallback = True
    items: list[dict[str, Any]] = []

    with get_db_connection() as conn:
        # 1. Try real aggregate activity signals if viewer_activity exists
        activity_scores: dict[int, float] = {}
        if _has_activity_table(conn):
            activity_scores = _score_from_activity(conn, window_days=window_days)

        if activity_scores:
            top_ids = [
                mid for mid, _ in sorted(activity_scores.items(), key=lambda kv: -kv[1])[: limit * 4]
            ]
            placeholders = ",".join("?" for _ in top_ids)
            rows = conn.execute(
                f"""
                SELECT * FROM movies
                WHERE id IN ({placeholders})
                  AND title IS NOT NULL AND title != ''
                  AND (COALESCE(poster, poster_url, '') != '' AND poster NOT LIKE '%logo.png%')
                  AND ({ADULT_EXCLUSION_SQL})
                  AND ({ANIMATION_EXCLUSION_SQL})
                """,
                top_ids,
            ).fetchall()
            scored_act = [(activity_scores[int(r["id"])], dict(r)) for r in rows]
            items = _deduplicate_and_rank(scored_act, limit=limit)
            if len(items) >= min(limit, 4):
                mode = "activity"
                is_fallback = False

        # 2. Deterministic fallback trending using verified catalogue signals (bounded query <= 450 rows)
        if len(items) < limit:
            existing_keys = {
                (_normalized_title(m.get("title")), str(m.get("year") or "").strip(), 1 if m.get("is_series") else 0)
                for m in items
            }
            candidate_rows = conn.execute(
                f"""
                SELECT * FROM movies
                WHERE title IS NOT NULL AND title != ''
                  AND (COALESCE(poster, poster_url, '') != '' AND poster NOT LIKE '%logo.png%')
                  AND ({ADULT_EXCLUSION_SQL})
                  AND ({ANIMATION_EXCLUSION_SQL})
                  AND (
                      CAST(COALESCE(NULLIF(year, ''), '0') AS INT) >= 2023
                      OR COALESCE(rating, 0) >= 7.0
                      OR last_quality_upgrade_at IS NOT NULL
                  )
                ORDER BY
                    COALESCE(rating, CAST(REPLACE(REPLACE(COALESCE(imdb, ''), 'IMDb: ', ''), '★ ', '') AS REAL), 0) DESC,
                    CAST(COALESCE(NULLIF(year, ''), '0') AS INT) DESC,
                    id DESC
                LIMIT 450
                """
            ).fetchall()

            # Count mirrors across sources for each canonical title (without letting mirrors duplicate)
            mirror_counts: dict[tuple[str, str], int] = defaultdict(int)
            raw_dicts = [dict(r) for r in candidate_rows]
            for d in raw_dicts:
                mirror_counts[(_normalized_title(d.get("title")), str(d.get("year") or "").strip())] += 1

            scored_fb: list[tuple[float, dict[str, Any]]] = []
            for d in raw_dicts:
                nt = _normalized_title(d.get("title"))
                yr = str(d.get("year") or "").strip()
                is_s = 1 if d.get("is_series") else 0
                if (nt, yr, is_s) in existing_keys:
                    continue
                mc = mirror_counts[(nt, yr)]
                scored_fb.append((_fallback_trending_score(d, mc, now_ts), d))

            needed = limit - len(items)
            fb_items = _deduplicate_and_rank(scored_fb, limit=needed)
            items.extend(fb_items)

    result = {
        "items": items[:limit],
        "total": len(items[:limit]),
        "mode": mode,
        "is_fallback": is_fallback,
    }

    with _trending_cache_lock:
        if len(_trending_cache) >= TRENDING_CACHE_MAX:
            oldest = min(_trending_cache, key=lambda k: _trending_cache[k][0])
            _trending_cache.pop(oldest, None)
        _trending_cache[cache_key] = (now_mono, result)

    return result
