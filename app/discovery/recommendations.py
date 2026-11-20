"""Personalized Recommended for You discovery engine for CINEMY.

Derives viewer preferences strictly from the authenticated viewer's watch history
(server-side `viewer_activity` scoped to `viewer_key` when present, plus optional
browser-local seed/exclude IDs belonging to that viewer).

Never leaks private viewing history across viewers, excludes already-watched titles,
deduplicates across sources, and falls back deterministically to Trending Now for new users.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from collections import defaultdict
from typing import Any, Optional

from ..api.routes_catalog import (
    ADULT_EXCLUSION_SQL,
    _format_row,
    _normalized_title,
    _source_priority,
    get_db_connection,
    is_movie_available_on_primary_sources,
)
from .trending import (
    _has_activity_table,
    _parse_rating,
    _parse_year,
    get_trending_titles,
)
from .popular import get_evergreen_titles

REC_CACHE_TTL = 120.0
REC_CACHE_MAX = 128
DEFAULT_REC_LIMIT = 50
MAX_REC_LIMIT = 50
MAX_SEED_IDS = 50

_rec_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}
_rec_cache_lock = threading.Lock()


def invalidate_recommendations_cache() -> None:
    with _rec_cache_lock:
        _rec_cache.clear()


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


def _extract_language_tag(row: dict[str, Any]) -> str:
    lang = str(row.get("language") or "").strip().lower()
    if lang:
        return lang
    q = str(row.get("quality") or "").strip().lower()
    if q in ("hindi", "punjabi", "tamil", "telugu", "bengali", "marathi", "gujarati"):
        return q
    if row.get("is_hindi_dubbed"):
        return "hindi"
    for g in _parse_json_list(row.get("genres")):
        gl = g.lower()
        if gl == "bollywood":
            return "hindi"
        if gl == "punjabi":
            return "punjabi"
        if gl == "hollywood":
            return "english"
    return ""


def _extract_quality_tier(row: dict[str, Any]) -> str:
    q = f"{row.get('best_quality') or ''} {row.get('quality') or ''}".lower()
    if "4k" in q or "2160" in q:
        return "4k"
    if "1080" in q or "bluray" in q or "web-dl" in q or "fhd" in q:
        return "1080p"
    if "720" in q or "hd" in q:
        return "720p"
    return ""


def _load_server_viewer_history(
    conn: sqlite3.Connection,
    viewer_key: str,
) -> tuple[dict[int, float], set[int]]:
    """
    Load per-viewer watch weights and substantially-watched/completed exclude IDs
    from `viewer_activity` (strictly scoped to `viewer_key`).
    """
    if not viewer_key or not _has_activity_table(conn):
        return {}, set()

    rows = conn.execute(
        """
        SELECT movie_id, watched_seconds, duration_seconds, created_at
        FROM viewer_activity
        WHERE viewer_id = ?
        ORDER BY created_at DESC
        LIMIT 100
        """,
        (viewer_key,),
    ).fetchall()

    now = int(time.time())
    weights: dict[int, float] = {}
    excluded: set[int] = set()
    for r in rows:
        mid = int(r["movie_id"])
        age_days = max(0.0, (now - int(r["created_at"] or now)) / 86400.0)
        recency = 1.0 / (1.0 + age_days / 14.0)
        watched = float(r["watched_seconds"] or 0.0)
        duration = float(r["duration_seconds"] or 0.0)
        ratio = (watched / duration) if duration > 0 else 0.0

        # Higher weight for completed / substantially watched titles
        w = (1.5 if ratio >= 0.7 else 1.0) * recency
        weights[mid] = max(weights.get(mid, 0.0), w)
        # Exclude completed or substantially watched titles (>=70%) from being recommended again
        if ratio >= 0.7 or watched >= 600:
            excluded.add(mid)

    return weights, excluded


def _build_user_profile(seed_rows: list[dict[str, Any]], seed_weights: dict[int, float]) -> dict[str, Any]:
    """Derive deterministic preference profile from the viewer's watched/saved titles."""
    genre_w: dict[str, float] = defaultdict(float)
    actor_w: dict[str, float] = defaultdict(float)
    director_w: dict[str, float] = defaultdict(float)
    lang_w: dict[str, float] = defaultdict(float)
    qual_w: dict[str, float] = defaultdict(float)
    movie_w = 0.0
    series_w = 0.0

    for row in seed_rows:
        mid = int(row["id"])
        w = seed_weights.get(mid, 1.0)
        for g in _parse_json_list(row.get("genres")):
            genre_w[g.lower()] += w
        for a in _parse_json_list(row.get("actors"))[:6]:
            actor_w[a.lower()] += w
        for d in _parse_json_list(row.get("director"))[:3]:
            director_w[d.lower()] += w
        lt = _extract_language_tag(row)
        if lt:
            lang_w[lt] += w
        qt = _extract_quality_tier(row)
        if qt:
            qual_w[qt] += w
        if row.get("is_series"):
            series_w += w
        else:
            movie_w += w

    def _normalize_weights(d: dict[str, float]) -> dict[str, float]:
        if not d:
            return {}
        m = max(d.values())
        return {k: v / m for k, v in d.items()} if m > 0 else {}

    total_type = movie_w + series_w
    return {
        "genres": _normalize_weights(genre_w),
        "actors": _normalize_weights(actor_w),
        "directors": _normalize_weights(director_w),
        "languages": _normalize_weights(lang_w),
        "qualities": _normalize_weights(qual_w),
        "movie_pref": (movie_w / total_type) if total_type > 0 else 0.5,
        "series_pref": (series_w / total_type) if total_type > 0 else 0.5,
        "top_genres": [k for k, _ in sorted(genre_w.items(), key=lambda kv: -kv[1])[:4]],
        "top_actors": [k for k, _ in sorted(actor_w.items(), key=lambda kv: -kv[1])[:4]],
        "top_directors": [k for k, _ in sorted(director_w.items(), key=lambda kv: -kv[1])[:3]],
    }


def _score_recommendation(row: dict[str, Any], profile: dict[str, Any]) -> float:
    """
    Deterministic weighted candidate scoring:
      - Genre match:    up to 38.0 (strong)
      - Actor overlap:  up to 28.0 (strong)
      - Director match: up to 24.0 (strong)
      - Media type:     up to 10.0 (medium)
      - Language:       up to 10.0 (medium)
      - Quality:        up to  6.0 (medium)
      - Rating:         up to  6.0 (secondary)
      - Recency:        up to  5.0 (secondary)
    """
    score = 0.0

    # 1. Genre similarity (strong)
    genres = [g.lower() for g in _parse_json_list(row.get("genres"))]
    if genres and profile["genres"]:
        g_hits = [profile["genres"][g] for g in genres if g in profile["genres"]]
        if g_hits:
            # Best genre + diminishing returns for multiple overlapping genres
            g_hits.sort(reverse=True)
            g_sum = g_hits[0] + sum(h * 0.45 for h in g_hits[1:3])
            score += min(38.0, g_sum * 24.0)

    # 2. Actor overlap (strong)
    actors = [a.lower() for a in _parse_json_list(row.get("actors"))]
    if actors and profile["actors"]:
        a_hits = [profile["actors"][a] for a in actors if a in profile["actors"]]
        if a_hits:
            score += min(28.0, sum(sorted(a_hits, reverse=True)[:2]) * 20.0)

    # 3. Director overlap (strong)
    directors = [d.lower() for d in _parse_json_list(row.get("director"))]
    if directors and profile["directors"]:
        d_hits = [profile["directors"][d] for d in directors if d in profile["directors"]]
        if d_hits:
            score += min(24.0, max(d_hits) * 24.0)

    # Require at least one content-affinity signal before adding medium/secondary signals
    if score <= 0.0:
        return 0.0

    # 4. Media type preference (medium)
    type_pref = profile["series_pref"] if row.get("is_series") else profile["movie_pref"]
    score += type_pref * 10.0

    # 5. Language preference (medium)
    lt = _extract_language_tag(row)
    if lt and lt in profile["languages"]:
        score += profile["languages"][lt] * 10.0

    # 6. Quality preference (medium)
    qt = _extract_quality_tier(row)
    if qt and qt in profile["qualities"]:
        score += profile["qualities"][qt] * 6.0

    # 7. Secondary signals: rating + recency
    rating = _parse_rating(row)
    if rating > 0:
        score += (rating / 10.0) * 6.0

    year = _parse_year(row)
    if year >= 2020:
        score += min(5.0, ((year - 2019) / 7.0) * 5.0)

    return round(score, 4)


def get_recommended_titles(
    viewer_key: str,
    *,
    limit: int = DEFAULT_REC_LIMIT,
    seed_ids: Optional[list[int]] = None,
    exclude_ids: Optional[list[int]] = None,
) -> dict[str, Any]:
    """
    Return personalized Recommended for You titles strictly scoped to `viewer_key`.
    Falls back deterministically to Trending Now when the viewer has insufficient watch history.
    """
    limit = min(MAX_REC_LIMIT, max(1, int(limit)))
    clean_seeds = sorted({int(x) for x in (seed_ids or []) if isinstance(x, int) and x > 0})[:MAX_SEED_IDS]
    clean_excludes = sorted({int(x) for x in (exclude_ids or []) if isinstance(x, int) and x > 0})[:MAX_SEED_IDS]

    cache_key = (viewer_key, tuple(clean_seeds), tuple(clean_excludes), limit)
    now_mono = time.monotonic()
    with _rec_cache_lock:
        cached = _rec_cache.get(cache_key)
        if cached and (now_mono - cached[0] < REC_CACHE_TTL):
            return cached[1]

    with get_db_connection() as conn:
        # 1. Gather server-side per-viewer history (if viewer_activity exists)
        srv_weights, srv_excludes = _load_server_viewer_history(conn, viewer_key)

        combined_weights: dict[int, float] = dict(srv_weights)
        for sid in clean_seeds:
            combined_weights.setdefault(sid, 1.0)

        all_exclude_ids: set[int] = set(srv_excludes) | set(clean_excludes) | set(clean_seeds)

        if not combined_weights:
            # New user with no watch history -> Evergreen Picks (distinct from Trending Now)
            trending_now = get_trending_titles(limit=limit)
            trending_ids = [int(m["id"]) for m in trending_now.get("items", []) if m.get("id")]
            trending_titles = {_normalized_title(m.get("title")) for m in trending_now.get("items", []) if _normalized_title(m.get("title"))}
            ev = get_evergreen_titles(
                limit=limit,
                exclude_ids=list(all_exclude_ids | set(trending_ids)),
                exclude_titles=trending_titles,
            )
            result = {
                "items": ev["items"],
                "total": ev["total"],
                "personalized": False,
                "mode": "evergreen_fallback",
            }
            with _rec_cache_lock:
                _rec_cache[cache_key] = (now_mono, result)
            return result

        # 2. Fetch metadata for viewer's seed titles in ONE bounded query
        seed_id_list = list(combined_weights.keys())[:MAX_SEED_IDS]
        ph = ",".join("?" for _ in seed_id_list)
        seed_rows = [
            dict(r)
            for r in conn.execute(
                f"SELECT * FROM movies WHERE id IN ({ph})",
                seed_id_list,
            ).fetchall()
        ]

        if not seed_rows:
            trending_now = get_trending_titles(limit=limit)
            trending_ids = [int(m["id"]) for m in trending_now.get("items", []) if m.get("id")]
            trending_titles = {_normalized_title(m.get("title")) for m in trending_now.get("items", []) if _normalized_title(m.get("title"))}
            ev = get_evergreen_titles(
                limit=limit,
                exclude_ids=list(all_exclude_ids | set(trending_ids)),
                exclude_titles=trending_titles,
            )
            result = {
                "items": ev["items"],
                "total": ev["total"],
                "personalized": False,
                "mode": "evergreen_fallback",
            }
            with _rec_cache_lock:
                _rec_cache[cache_key] = (now_mono, result)
            return result

        # Track normalized titles of all watched/excluded items so mirror copies are also excluded
        excluded_norm_titles: set[str] = {
            _normalized_title(r.get("title")) for r in seed_rows if _normalized_title(r.get("title"))
        }
        extra_ex_ids = [eid for eid in all_exclude_ids if eid not in set(seed_id_list)][:MAX_SEED_IDS]
        if extra_ex_ids:
            eph = ",".join("?" for _ in extra_ex_ids)
            for r in conn.execute(f"SELECT title FROM movies WHERE id IN ({eph})", extra_ex_ids).fetchall():
                nt = _normalized_title(r["title"])
                if nt:
                    excluded_norm_titles.add(nt)

        profile = _build_user_profile(seed_rows, combined_weights)

        # 3. Fetch ONE bounded candidate pool (<= 300 rows) matching top genres / actors / directors
        affinity_clauses: list[str] = []
        affinity_args: list[Any] = []
        for g in profile["top_genres"]:
            affinity_clauses.append("genres LIKE ?")
            affinity_args.append(f"%{g}%")
        for a in profile["top_actors"]:
            affinity_clauses.append("actors LIKE ?")
            affinity_args.append(f"%{a}%")
        for d in profile["top_directors"]:
            affinity_clauses.append("director LIKE ?")
            affinity_args.append(f"%{d}%")

        if not affinity_clauses:
            trending_now = get_trending_titles(limit=limit)
            trending_ids = [int(m["id"]) for m in trending_now.get("items", []) if m.get("id")]
            trending_titles = {_normalized_title(m.get("title")) for m in trending_now.get("items", []) if _normalized_title(m.get("title"))}
            ev = get_evergreen_titles(
                limit=limit,
                exclude_ids=list(all_exclude_ids | set(trending_ids)),
                exclude_titles=trending_titles,
            )
            result = {
                "items": ev["items"],
                "total": ev["total"],
                "personalized": False,
                "mode": "evergreen_fallback",
            }
            with _rec_cache_lock:
                _rec_cache[cache_key] = (now_mono, result)
            return result

        ex_list = list(all_exclude_ids)[:100]
        ex_sql = f"AND id NOT IN ({','.join('?' for _ in ex_list)})" if ex_list else ""

        candidate_rows = conn.execute(
            f"""
            SELECT * FROM movies
            WHERE title IS NOT NULL AND title != ''
              AND (COALESCE(poster, poster_url, '') != '' AND poster NOT LIKE '%logo.png%')
              AND ({ADULT_EXCLUSION_SQL})
              AND ({' OR '.join(affinity_clauses)})
              {ex_sql}
            ORDER BY
                COALESCE(rating, CAST(REPLACE(REPLACE(COALESCE(imdb, ''), 'IMDb: ', ''), '★ ', '') AS REAL), 0) DESC,
                CAST(COALESCE(NULLIF(year, ''), '0') AS INT) DESC,
                id DESC
            LIMIT 300
            """,
            affinity_args + ex_list,
        ).fetchall()

    # 4. Score & deduplicate candidates deterministically
    dedup: dict[tuple[str, str, int], tuple[float, int, dict[str, Any]]] = {}
    for r in candidate_rows:
        d = dict(r)
        if d.get("source") == "movies7" and is_movie_available_on_primary_sources(d.get("title"), d.get("year")):
            continue
        nt = _normalized_title(d.get("title"))
        if not nt or nt in excluded_norm_titles:
            continue
        score = _score_recommendation(d, profile)
        if score <= 0.0:
            continue

        key = (nt, str(d.get("year") or "").strip(), 1 if d.get("is_series") else 0)
        prio = _source_priority(d.get("source"))
        existing = dedup.get(key)
        if existing is None:
            dedup[key] = (score, prio, d)
        else:
            prev_score, prev_prio, _ = existing
            if score > prev_score + 1.5 or (abs(score - prev_score) <= 1.5 and prio < prev_prio):
                dedup[key] = (max(score, prev_score), min(prio, prev_prio), d)

    ordered = sorted(
        dedup.values(),
        key=lambda e: (-e[0], e[1], -(int(e[2].get("id") or 0))),
    )
    items = [_format_row(row) for _, _, row in ordered[:limit]]

    personalized = len(items) > 0
    mode = "personalized" if personalized else "evergreen_fallback"

    # Fall back to Evergreen Picks (excluding Trending) only if zero personalized matches were found
    if not items:
        trending_now = get_trending_titles(limit=limit)
        trending_ids = [int(m["id"]) for m in trending_now.get("items", []) if m.get("id")]
        trending_titles = {_normalized_title(m.get("title")) for m in trending_now.get("items", []) if _normalized_title(m.get("title"))}
        ev = get_evergreen_titles(
            limit=limit,
            exclude_ids=list(all_exclude_ids | set(trending_ids)),
            exclude_titles=excluded_norm_titles | trending_titles,
        )
        items = ev["items"][:limit]

    result = {
        "items": items[:limit],
        "total": len(items[:limit]),
        "personalized": personalized,
        "mode": mode,
    }

    with _rec_cache_lock:
        if len(_rec_cache) >= REC_CACHE_MAX:
            oldest = min(_rec_cache, key=lambda k: _rec_cache[k][0])
            _rec_cache.pop(oldest, None)
        _rec_cache[cache_key] = (now_mono, result)

    return result
