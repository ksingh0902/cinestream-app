# app/api/routes_catalog.py
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..adapters import registry
from ..adapters.ask4movie.sync import connect

router = APIRouter()


@router.get("/api/sources")
def sources():
    """R12: Report each adapter's status, items count, and player kind."""
    return registry.health()


def _format_row(row: dict) -> dict:
    d = dict(row)
    # Ensure poster_url and poster are populated
    if not d.get("poster_url") and d.get("poster"):
        d["poster_url"] = d["poster"]
    if not d.get("poster") and d.get("poster_url"):
        d["poster"] = d["poster_url"]
    if not d.get("detail_url") and d.get("url"):
        d["detail_url"] = d["url"]
    if not d.get("url") and d.get("detail_url"):
        d["url"] = d["detail_url"]
    if not d.get("player_kind"):
        d["player_kind"] = "hls" if d.get("source") == "yomovies" else "iframe"

    # Flag Hindi dubbed Hollywood and foreign titles
    is_dub = bool(d.get("is_hindi_dubbed"))
    if not is_dub:
        t = (d.get("title") or "").lower()
        g_raw = str(d.get("genres") or "").lower()
        q = (d.get("quality") or "").lower()
        if any(k in g_raw for k in ("hollywood dubbed", "dual audio", "unofficial dubbed", "hindi dubbed")):
            is_dub = True
        elif any(k in t for k in ("hindi dubbed", "dual audio", "(hindi)", "[hindi]", "dual-audio")):
            is_dub = True
        elif q in ("hindi", "dual audio"):
            is_dub = True
    d["is_hindi_dubbed"] = is_dub

    for k in ("genres", "actors", "director", "country", "embeds", "downloads"):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass
    return d


ADULT_EXCLUSION_SQL = (
    "quality != '18+' AND (quality NOT LIKE '%18+%' OR quality IS NULL) "
    "AND (genres NOT LIKE '%\"Erotic Movies\"%' OR genres IS NULL) "
    "AND title NOT LIKE '%(Ullu%' "
    "AND title NOT LIKE '%(PrimeShots%' "
    "AND title NOT LIKE '%(Hunters%' "
    "AND title NOT LIKE '%(WOOW%' "
    "AND title NOT LIKE '%(HuntCinema%' "
    "AND title NOT LIKE '%(Mastiplay%' "
    "AND title NOT LIKE '%(BulbulPlay%' "
    "AND title NOT LIKE '%(Besharams%' "
    "AND title NOT LIKE '%(Kaddu%' "
    "AND title NOT LIKE '%(DesiPrime%' "
    "AND title NOT LIKE '%(Hotshots%' "
    "AND title NOT LIKE '%(MoodX%' "
    "AND title NOT LIKE '%(Voovi%' "
    "AND title NOT LIKE '%(Chikooflix%' "
    "AND title NOT LIKE '%(Bigshots%' "
    "AND title NOT LIKE '%(Atrangii%' "
    "AND title NOT LIKE '%(Altbalaji%' "
    "AND title NOT LIKE '%(Jugnutv%' "
    "AND title NOT LIKE '%(Rabbit%'"
)

COMMON_SYNONYMS = {
    "phela": ["pehla", "phela"],
    "phel": ["pehl", "phel"],
    "pyaar": ["pyaar", "pyar"],
    "pyar": ["pyar", "pyaar"],
    "squidgame": ["squid game", "squid"],
    "spiderman": ["spider-man", "spider man"],
    "ironman": ["iron man", "iron-man"],
    "batman": ["bat-man", "bat man"],
    "punkjabi": ["punjabi"],
    "pujabi": ["punjabi"],
    "panjabi": ["punjabi"],
    "bolywood": ["bollywood"],
    "holywood": ["hollywood"],
}


def _build_search_clause(q_str: str) -> tuple[str, list]:
    import re
    q_str = (q_str or "").strip()
    if not q_str:
        return "1=1", []
    clauses = ["title LIKE ?"]
    params = [f"%{q_str}%"]
    words = [w for w in re.split(r'[\s\-]+', q_str.lower()) if len(w) >= 2]
    if words:
        word_clauses = []
        token_params = []
        for w in words:
            syns = COMMON_SYNONYMS.get(w, [w])
            sub_c = " OR ".join(["title LIKE ?" for _ in syns])
            word_clauses.append(f"({sub_c})")
            token_params.extend([f"%{s}%" for s in syns])
        clauses.append(f"({' AND '.join(word_clauses)})")
        params.extend(token_params)
    return f"({' OR '.join(clauses)})", params


@router.get("/api/movies")
def movies(
    source: Optional[str] = None,
    q: Optional[str] = None,
    genre: Optional[str] = None,
    year: Optional[str] = None,
    series: Optional[int] = None,
    sort: str = "recent",
    page: int = 1,
    per_page: int = 48,
):
    where = ["title IS NOT NULL AND title != ''"]
    args = []

    if series is not None:
        where.append("is_series = ?")
        args.append(series)
    elif source == "yomovies":
        where.append("is_series = 0")
    elif not source:
        # Yomovies inside global view shows only movies, while other sources show both
        where.append("(source != 'yomovies' OR is_series = 0)")

    if source:
        where.append("source = ?")
        args.append(source)
    else:
        # Global view excludes adult content from Yomovies
        where.append(f"(source != 'yomovies' OR ({ADULT_EXCLUSION_SQL}))")

    q_str = (q or "").strip()
    if q_str:
        sq_clause, sq_params = _build_search_clause(q_str)
        where.append(sq_clause)
        args.extend(sq_params)

    if genre:
        if genre.lower() == "bollywood":
            where.append("(genres LIKE ? OR quality = ? OR title LIKE ?) AND genres NOT LIKE '%\"Punjabi\"%' AND title NOT LIKE '%Punjabi%'")
            args.extend([f'%"{genre}"%', genre, f"%{genre}%"])
        elif genre.lower() in ("hindi dubbed", "hollywood dubbed", "dual audio"):
            where.append("(is_hindi_dubbed = 1 OR genres LIKE ? OR quality = ? OR title LIKE ?)")
            args.extend([f'%"{genre}"%', genre, f"%{genre}%"])
        else:
            where.append("(genres LIKE ? OR quality = ? OR title LIKE ?)")
            args.extend([f'%"{genre}"%', genre, f"%{genre}%"])

    if year:
        where.append("year = ?")
        args.append(year)

    where_clause = " AND ".join(where)
    count_sql = f"SELECT COUNT(*) FROM movies WHERE {where_clause}"

    # Ordering:
    if q_str:
        order = "CASE WHEN title LIKE ? THEN 0 WHEN title LIKE ? THEN 1 ELSE 2 END, CAST(year AS INT) DESC, id ASC"
        query_sql = (
            f"SELECT * FROM movies WHERE {where_clause} "
            f"ORDER BY {order} LIMIT ? OFFSET ?"
        )
        query_args = args + [f"{q_str}%", f"%{q_str}%", per_page, (page - 1) * per_page]
    elif sort in ("imdb", "rating"):
        query_sql = (
            f"SELECT * FROM movies WHERE {where_clause} "
            f"ORDER BY COALESCE(rating, CAST(REPLACE(REPLACE(imdb, 'IMDb: ', ''), '★ ', '') AS REAL), 0) DESC, CAST(year AS INT) DESC, id ASC "
            f"LIMIT ? OFFSET ?"
        )
        query_args = args + [per_page, (page - 1) * per_page]
    elif sort == "title":
        query_sql = (
            f"SELECT * FROM movies WHERE {where_clause} "
            f"ORDER BY title ASC, CAST(year AS INT) DESC, id ASC "
            f"LIMIT ? OFFSET ?"
        )
        query_args = args + [per_page, (page - 1) * per_page]
    else:
        # Default ("recent" / "year"):
        # Interleave sources (ask4movie and yomovies) with the latest released movies on top (e.g. Udta Teer, Gajab Raat),
        # ordered by year descending and id ascending.
        query_sql = f"""
            WITH filtered AS (
                SELECT * FROM movies WHERE {where_clause}
            ),
            ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY source 
                    ORDER BY 
                        CAST(COALESCE(NULLIF(year, ''), '0') AS INT) DESC, 
                        COALESCE(updated_at, 0) DESC,
                        id ASC
                ) AS src_rank
                FROM filtered
            )
            SELECT * FROM ranked 
            ORDER BY src_rank ASC, source ASC 
            LIMIT ? OFFSET ?
        """
        query_args = args + [per_page, (page - 1) * per_page]

    with connect() as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute(count_sql, args).fetchone()[0]
        raw_rows = conn.execute(query_sql, query_args).fetchall()
        rows = [_format_row(dict(r)) for r in raw_rows]

    return {"total": total, "page": page, "per_page": per_page, "items": rows}


@router.get("/api/movie/{movie_id}")
def movie(movie_id: int):
    with connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM movies WHERE id = ?", (movie_id,)).fetchone()
    if not row:
        raise HTTPException(404, "not found")

    d = _format_row(dict(row))

    # Cross-source dedupe view (R14): check if same title + year exists on another source
    raw_title = d.get("title") or ""
    import re
    clean_title = re.sub(r'\s*\(\d{4}\).*', '', raw_title).strip()
    if clean_title:
        with connect() as conn:
            conn.row_factory = sqlite3.Row
            alts = conn.execute(
                "SELECT id, source, title, year, player_kind, is_hindi_dubbed FROM movies "
                "WHERE (title = ? OR title LIKE ? OR title LIKE ?) AND id != ? LIMIT 3",
                (clean_title, f"{clean_title} (%", f"{clean_title}%", movie_id),
            ).fetchall()
            d["also_available_on"] = [dict(a) for a in alts]

    return d
