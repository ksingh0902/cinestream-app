# app/api/routes_catalog.py
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..adapters import registry

router = APIRouter()

_FILTER_CACHE_TTL_SECONDS = 600.0  # 10 minutes cache per filter
_FILTER_CACHE_MAX_ENTRIES = 512
_filter_cache: dict[tuple, tuple[float, list[dict]]] = {}
_filter_cache_lock = threading.Lock()


def get_db_connection() -> sqlite3.Connection:
    """Ultra-fast, read-optimized SQLite connection with 30s busy timeout and WAL mode."""
    target_path = "cinemymovies.sqlite3" if os.path.exists("cinemymovies.sqlite3") else "yomovies.db"
    conn = sqlite3.connect(target_path, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA cache_size = -64000")
    conn.execute("PRAGMA mmap_size = 268435456")
    conn.row_factory = sqlite3.Row
    return conn


def _normalized_title(title: str | None) -> str:
    value = (title or "").lower()
    value = re.sub(r"\s*[\[(]\s*(?:19|20)\d{2}\s*[\])]", " ", value)
    value = re.sub(r"\s+(?:19|20)\d{2}\s*$", " ", value)
    value = re.sub(r"\b(?:hindi dubbed|hollywood dubbed|dual[ -]?audio|english dubbed|english|hindi|punjabi|tamil|telugu)\b", " ", value)
    # Strip Season / Episode / Part / Volume tags (e.g. Season 1, S01, Episode 1-8, Part 2)
    value = re.sub(r"\b(?:season\s*\d+|s\d+|episode\s*\d+|ep\s*\d+|part\s*\d+|vol\s*\d+)\b", " ", value)
    # Strip OTT platform tags and release descriptors (e.g. Netflix, Amazon Prime, Hotstar, Zee5, SonyLIV, etc.)
    value = re.sub(r"\b(?:netflix|amazon|prime|hotstar|zee5|sonyliv|hungama|voot|jiocinema|apple tv|disney|hbo|hulu|originals?)\b", " ", value)
    value = re.sub(r"\b(?:watch online.*|full movie|web series)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


_non_m7_title_keys: set[tuple[str, str]] | None = None
_non_m7_base_titles: set[str] | None = None
_non_m7_title_keys_lock = threading.Lock()


def _get_non_m7_title_keys() -> tuple[set[tuple[str, str]], set[str]]:
    global _non_m7_title_keys, _non_m7_base_titles
    with _non_m7_title_keys_lock:
        if _non_m7_title_keys is not None and _non_m7_base_titles is not None:
            return _non_m7_title_keys, _non_m7_base_titles
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT title, year FROM movies WHERE source IN ('yomovies', 'dooflix', 'ask4movie') AND title IS NOT NULL"
            ).fetchall()
            keys = set()
            base_titles = set()
            for r in rows:
                nt = _normalized_title(r["title"])
                yr = str(r["year"] or "").strip()
                if nt:
                    keys.add((nt, yr))
                    keys.add((nt, ""))
                    base_titles.add(nt)
            _non_m7_title_keys = keys
            _non_m7_base_titles = base_titles
            return _non_m7_title_keys, _non_m7_base_titles


def is_movie_available_on_primary_sources(title: str | None, year: str | int | None) -> bool:
    """Returns True if this movie is already available on Yomovies, Dooflix, or Ask4movie."""
    if not title:
        return False
    keys, base_titles = _get_non_m7_title_keys()
    nt = _normalized_title(title)
    if not nt:
        return False
    yr = str(year or "").strip()
    if (nt, yr) in keys or (nt, "") in keys:
        return True
    if yr.isdigit():
        y_int = int(yr)
        if (nt, str(y_int - 1)) in keys or (nt, str(y_int + 1)) in keys:
            return True
    if nt in base_titles:
        return True
    return False


def invalidate_catalog_cache() -> None:
    """Clear in-memory catalog cache when new titles are synced or updated."""
    global _non_m7_title_keys, _non_m7_base_titles
    with _filter_cache_lock:
        _filter_cache.clear()
    with _non_m7_title_keys_lock:
        _non_m7_title_keys = None
        _non_m7_base_titles = None


def prewarm_catalog_cache() -> None:
    """Lazy cache warming: views are cached on-demand when requested by users.
    Boot-time batch prewarming is disabled to protect VM CPU and memory.
    """
    return


def _audio_edition(item: dict) -> str:
    text = " ".join(str(item.get(key) or "").lower() for key in ("title", "genres", "quality", "language", "language_code"))
    if "dual audio" in text or "dual-audio" in text:
        return "dual_audio"
    if item.get("is_hindi_dubbed") or any(marker in text for marker in ("hindi dubbed", "hollywood dubbed", "unofficial dubbed")):
        return "hindi_dubbed"
    code = str(item.get("language_code") or "").lower().strip()
    language = str(item.get("language") or "").lower()
    if code in ("hi", "hin") or "hindi" in language:
        return "hindi"
    if code in ("en", "eng") or "english" in language:
        return "english"
    return "unknown"


def _source_priority(source: str | None, edition: str = "") -> int:
    order = ("yomovies", "dooflix", "ask4movie", "movies7")
    try:
        return order.index(source or "")
    except ValueError:
        return len(order)


def _edition_key(item: dict) -> tuple[str, str, str]:
    return (_normalized_title(item.get("title")), str(item.get("year") or ""), _audio_edition(item))


def _group_ordered_editions(items: list[dict]) -> list[dict]:
    ordered_keys: list[tuple[str, str, str]] = []
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for item in items:
        key = _edition_key(item)
        if not key[0]:
            key = (f"id:{item.get('id')}", key[1], key[2])
        if key not in groups:
            ordered_keys.append(key)
            groups[key] = []
        groups[key].append(item)
    grouped = []
    for key in ordered_keys:
        candidates = groups[key]
        edition = key[2]
        candidates.sort(key=lambda row: (_source_priority(row.get("source"), edition), -(row.get("updated_at") or 0), row.get("id") or 0))
        primary = candidates[0]
        primary["audio_edition"] = edition
        primary["available_source_count"] = len({row.get("source") for row in candidates})
        grouped.append(primary)
    return grouped


@router.get("/api/sources")
def sources():
    """R12: Report each adapter's status, items count, and player kind."""
    return registry.health()


def _format_row(row: dict) -> dict:
    d = dict(row)
    # Sanitize invalid dummy posters (e.g. Ask4Movie logo.png placeholders or relative assets)
    for k in ("poster", "poster_url"):
        val = str(d.get(k) or "").strip()
        if not val or "logo.png" in val or val.startswith("/assets/") or val in ("None", "null"):
            d[k] = None

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
    "(genres NOT LIKE '%\"Erotic Movies\"%' OR genres IS NULL) "
    "AND (genres NOT LIKE '%\"Erotic\"%' OR genres IS NULL) "
    "AND (genres NOT LIKE '%\"Hot Series\"%' OR genres IS NULL) "
    "AND (url NOT LIKE '%/genre/erotic-movies/%' OR url IS NULL) "
    "AND (url NOT LIKE '%/genre/hot-series/%' OR url IS NULL) "
    "AND (url NOT LIKE '%/hot-series/%' OR url IS NULL) "
    "AND title NOT LIKE '%Erotic%' "
    "AND title NOT LIKE '%Hot Series%' "
    "AND title NOT LIKE '%Hot Web Series%' "
    "AND title NOT LIKE '%Ullu%' "
    "AND title NOT LIKE '%Altbalaji%' "
    "AND title NOT LIKE '%Alt Balaji%' "
    "AND title NOT LIKE '%WOOW%' "
    "AND title NOT LIKE '%PrimePlay%' "
    "AND title NOT LIKE '%Prime Play%' "
    "AND title NOT LIKE '%Nuefliks%' "
    "AND title NOT LIKE '%MoodX%' "
    "AND title NOT LIKE '%Besharams%' "
    "AND title NOT LIKE '%Feneomovies%' "
    "AND title NOT LIKE '%Feneo%' "
    "AND title NOT LIKE '%Gemplex%' "
    "AND title NOT LIKE '%BoomMovies%' "
    "AND title NOT LIKE '%Boom Movies%' "
    "AND title NOT LIKE '%Night Show%' "
    "AND title NOT LIKE '%Hootzy%' "
    "AND title NOT LIKE '%Bambooflix%' "
    "AND title NOT LIKE '%Eightshots%' "
    "AND title NOT LIKE '%Eight Shots%' "
    "AND title NOT LIKE '%BananaPrime%' "
    "AND title NOT LIKE '%Banana Prime%' "
    "AND title NOT LIKE '%Chikooflix%' "
    "AND title NOT LIKE '%Cinemadosti%' "
    "AND title NOT LIKE '%CliffMovies%' "
    "AND title NOT LIKE '%Flixsksmovies%' "
    "AND title NOT LIKE '%Balloons%' "
    "AND title NOT LIKE '%Piliflix%' "
    "AND title NOT LIKE '%I-Entertainment%' "
    "AND title NOT LIKE '%HotHit%' "
    "AND title NOT LIKE '%Glamheart%' "
    "AND title NOT LIKE '%Fliz Movies%' "
    "AND title NOT LIKE '%FlizMovies%' "
    "AND title NOT LIKE '%(Fliz%' "
    "AND title NOT LIKE '% Fliz%' "
    "AND title NOT LIKE '%(Hunters%' "
    "AND title NOT LIKE '%Hunters Original%' "
    "AND title NOT LIKE '%Hunters App%' "
    "AND title NOT LIKE '%Gupchup%' "
    "AND title NOT LIKE '%Primeflix%' "
    "AND title NOT LIKE '%HotMasti%' "
    "AND title NOT LIKE '%MastiPrime%' "
    "AND title NOT LIKE '%Lootlo%' "
    "AND title NOT LIKE '%Big Movie Zoo%' "
    "AND title NOT LIKE '%11upmovies%' "
    "AND title NOT LIKE '%Hotprime%' "
    "AND title NOT LIKE '%Worldprime%' "
    "AND title NOT LIKE '%PrimeShots%' "
    "AND title NOT LIKE '%Prime Shots%' "
    "AND title NOT LIKE '%Hotshots%' "
    "AND title NOT LIKE '%HotX%' "
    "AND title NOT LIKE '%VooVi%' "
    "AND title NOT LIKE '%Voovi%' "
    "AND title NOT LIKE '%Kooku%' "
    "AND title NOT LIKE '%(Rabbit%' "
    "AND title NOT LIKE '%Rabbit Original%' "
    "AND title NOT LIKE '%Rabbit Movies%' "
    "AND title NOT LIKE '%Cineprime%' "
    "AND title NOT LIKE '%Cine Prime%' "
    "AND title NOT LIKE '%RedPrime%' "
    "AND title NOT LIKE '%Red Prime%' "
    "AND title NOT LIKE '%Feelit%' "
    "AND title NOT LIKE '%Yessma%' "
    "AND title NOT LIKE '%Jalva%' "
    "AND title NOT LIKE '%HuntCinema%' "
    "AND title NOT LIKE '%Mastiplay%' "
    "AND title NOT LIKE '%BulbulPlay%' "
    "AND title NOT LIKE '%Kaddu%' "
    "AND title NOT LIKE '%DesiPrime%' "
    "AND title NOT LIKE '%Atrangii%' "
    "AND title NOT LIKE '%Jugnutv%' "
    "AND title NOT LIKE '%Honeymoon Couples%' "
    "AND title NOT LIKE '%Tempt Original%' "
    "AND title NOT LIKE '%(Tempt%' "
    "AND (synopsis NOT LIKE '%WOOW Original%' OR synopsis IS NULL) "
    "AND (synopsis NOT LIKE '%WOOW%' OR synopsis IS NULL) "
    "AND (synopsis NOT LIKE '%Tempt Original%' OR synopsis IS NULL)"
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
    filter_key = (
        source or "",
        (q or "").strip().lower(),
        (genre or "").strip().lower(),
        year or "",
        series,
        sort,
    )
    now = time.monotonic()

    # Instant memory cache check (0.01ms)
    with _filter_cache_lock:
        cached = _filter_cache.get(filter_key)
        if cached and (now - cached[0] < _FILTER_CACHE_TTL_SECONDS):
            items_list = cached[1]
            total = len(items_list)
            offset = (page - 1) * per_page
            return {
                "total": total,
                "page": page,
                "per_page": per_page,
                "items": items_list[offset:offset + per_page],
            }

    where = ["title IS NOT NULL AND title != ''"]
    args = []

    if series is not None:
        where.append("is_series = ?")
        args.append(series)

    if source:
        where.append("source = ?")
        args.append(source)
    where.append(f"({ADULT_EXCLUSION_SQL})")

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

    # Ordering:
    if q_str:
        order = "CASE WHEN title LIKE ? THEN 0 WHEN title LIKE ? THEN 1 ELSE 2 END, CAST(year AS INT) DESC, id ASC"
        query_sql = f"SELECT * FROM movies WHERE {where_clause} ORDER BY {order}"
        query_args = args + [f"{q_str}%", f"%{q_str}%"]
    elif sort in ("imdb", "rating"):
        query_sql = (
            f"SELECT * FROM movies WHERE {where_clause} "
            f"ORDER BY COALESCE(rating, CAST(REPLACE(REPLACE(imdb, 'IMDb: ', ''), '★ ', '') AS REAL), 0) DESC, CAST(year AS INT) DESC, id ASC"
        )
        query_args = args
    elif sort == "title":
        query_sql = f"SELECT * FROM movies WHERE {where_clause} ORDER BY title ASC, CAST(year AS INT) DESC, id ASC"
        query_args = args
    else:
        # Default ("recent" / "year"):
        # Interleave sources with the latest released movies on top, ordered by year descending and id ascending.
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
        """
        query_args = args

    with get_db_connection() as conn:
        raw_rows = conn.execute(query_sql, query_args).fetchall()
        if source:
            if source == "movies7":
                formatted = [
                    _format_row(dict(r)) for r in raw_rows
                    if not is_movie_available_on_primary_sources(dict(r).get("title"), dict(r).get("year"))
                ]
            else:
                formatted = [_format_row(dict(r)) for r in raw_rows]
            items_list = formatted
        else:
            formatted = []
            for r in raw_rows:
                d = dict(r)
                if d.get("source") == "movies7" and is_movie_available_on_primary_sources(d.get("title"), d.get("year")):
                    continue
                formatted.append(_format_row(d))
            items_list = _group_ordered_editions(formatted)

    with _filter_cache_lock:
        if len(_filter_cache) >= _FILTER_CACHE_MAX_ENTRIES:
            oldest_key = min(_filter_cache, key=lambda k: _filter_cache[k][0])
            _filter_cache.pop(oldest_key, None)
        _filter_cache[filter_key] = (now, items_list)

    total = len(items_list)
    offset = (page - 1) * per_page
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": items_list[offset:offset + per_page],
    }


@router.get("/api/movie/{movie_id}")
def movie(movie_id: int):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM movies WHERE id = ?", (movie_id,)).fetchone()
    if not row:
        raise HTTPException(404, "not found")

    d = _format_row(dict(row))

    title_key = _normalized_title(d.get("title"))
    current_edition = _audio_edition(d)
    d["audio_edition"] = current_edition
    if title_key:
        with get_db_connection() as conn:
            candidates = conn.execute(
                f"SELECT * FROM movies WHERE COALESCE(CAST(year AS TEXT), '') = ? AND id != ? AND ({ADULT_EXCLUSION_SQL})",
                (str(d.get("year") or ""), movie_id),
            ).fetchall()
        matches = [_format_row(dict(row)) for row in candidates if _normalized_title(dict(row).get("title")) == title_key]
        same_edition = [row for row in matches if _audio_edition(row) == current_edition]
        same_edition.sort(key=lambda row: (_source_priority(row.get("source"), current_edition), row.get("id") or 0))
        d["available_sources"] = same_edition
        d["also_available_on"] = same_edition
        other_groups: dict[str, list[dict]] = {}
        for row in matches:
            edition = _audio_edition(row)
            if edition != current_edition:
                other_groups.setdefault(edition, []).append(row)
        d["other_editions"] = []
        for edition, edition_rows in other_groups.items():
            edition_rows.sort(key=lambda row: (_source_priority(row.get("source"), edition), row.get("id") or 0))
            representative = edition_rows[0]
            representative["audio_edition"] = edition
            representative["available_source_count"] = len({row.get("source") for row in edition_rows})
            d["other_editions"].append(representative)

    return d


TMDB_SEASONS_CACHE: dict[str, dict] = {}


def _get_clean_series_name(title: str) -> str:
    clean = re.sub(r"\s*\(?(?:19|20)\d{2}\)?", " ", title or "")
    clean = re.sub(r"\bSeason\s*\d+.*", " ", clean, flags=re.I)
    clean = re.sub(r"\bS\d{1,2}\s*E\d{1,3}.*", " ", clean, flags=re.I)
    clean = re.sub(r"\bEpisode\s*[\d\-]+.*", " ", clean, flags=re.I)
    clean = re.sub(r"\b(?:hindi dubbed|hollywood dubbed|dual audio|english dubbed|netflix|amazon prime|hotstar specials|unofficial dubbed)\b.*", " ", clean, flags=re.I)
    return re.sub(r"\s+", " ", clean).strip()


def _lookup_tmdb_tv_id(title: str, year: str | None = None) -> str | None:
    import httpx
    clean = _get_clean_series_name(title)
    if not clean:
        return None
    # Do NOT pass first_air_date_year when searching for TV series because scraped titles
    # reflect the current season release year rather than the show's original debut year
    params = {"api_key": "15d2ea6d0dc1d476efbca3eba2b9bbfb", "query": clean}
    try:
        r = httpx.get("https://api.tmdb.org/3/search/tv", params=params, timeout=5)
        if r.status_code == 200:
            res = r.json().get("results") or []
            if res:
                clean_lower = clean.lower()
                for item in res:
                    if (item.get("name") or "").lower() == clean_lower:
                        return str(item["id"])
                res.sort(key=lambda x: x.get("popularity", 0), reverse=True)
                return str(res[0]["id"])
    except Exception:
        pass
    return None


@router.get("/api/series/{movie_id}/seasons")
def series_seasons(movie_id: int):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM movies WHERE id = ?", (movie_id,)).fetchone()

    if not row:
        raise HTTPException(404, "not found")

    title = row["title"] or ""
    is_series = bool(row["is_series"]) or bool(
        re.search(r"\b(?:season|episode|s\d{1,2}e\d{1,3})\b", title, re.I)
    )
    if not is_series:
        return {"is_series": False, "seasons": []}

    clean_name = _get_clean_series_name(title) or title
    tmdb_id = row["tmdb_id"]

    # Parse current season / episode from the row's title
    cur_s_m = re.search(r"\bSeason\s*(\d+)\b", title, re.I)
    cur_e_m = re.search(r"\bEpisode\s*(\d+)\b", title, re.I)
    current_season = int(cur_s_m.group(1)) if cur_s_m else 1
    current_episode = int(cur_e_m.group(1)) if cur_e_m else 1

    # Find sibling rows in database (excluding adult/erotic)
    db_episodes = {}
    with get_db_connection() as conn:
        query = f"SELECT id, title, source, tmdb_id FROM movies WHERE title LIKE ? AND ({ADULT_EXCLUSION_SQL}) ORDER BY id ASC"
        siblings = conn.execute(query, (f"{clean_name}%",)).fetchall()
        for sib in siblings:
            s_m = re.search(r"\bSeason\s*(\d+)\b", sib["title"] or "", re.I)
            e_m = re.search(r"\bEpisode\s*(\d+)\b", sib["title"] or "", re.I)
            s_num = int(s_m.group(1)) if s_m else 1
            e_num = int(e_m.group(1)) if e_m else 1
            if not tmdb_id and sib["tmdb_id"]:
                tmdb_id = sib["tmdb_id"]
            db_episodes[(s_num, e_num)] = dict(sib)

    if not tmdb_id:
        tmdb_id = _lookup_tmdb_tv_id(clean_name, str(row["year"] or ""))
        if tmdb_id:
            try:
                target_path = "cinemymovies.sqlite3" if os.path.exists("cinemymovies.sqlite3") else "yomovies.db"
                with sqlite3.connect(target_path, timeout=10) as write_conn:
                    write_conn.execute("UPDATE movies SET tmdb_id=? WHERE id=?", (tmdb_id, movie_id))
                    write_conn.commit()
            except Exception:
                pass

    seasons = []

    # If TMDB ID is available, fetch full season & episode hierarchy from TMDB TV API
    if tmdb_id:
        tid_str = str(tmdb_id)
        tmdb_data = TMDB_SEASONS_CACHE.get(tid_str)
        if not tmdb_data:
            import httpx
            try:
                r = httpx.get(
                    f"https://api.tmdb.org/3/tv/{tid_str}",
                    params={"api_key": "15d2ea6d0dc1d476efbca3eba2b9bbfb"},
                    timeout=5,
                )
                if r.status_code == 200:
                    tmdb_data = r.json()
                    TMDB_SEASONS_CACHE[tid_str] = tmdb_data
            except Exception:
                pass

        if tmdb_data and "seasons" in tmdb_data:
            raw_seasons = [
                s for s in tmdb_data["seasons"]
                if s.get("season_number", 0) > 0 or len(tmdb_data["seasons"]) == 1
            ]
            raw_seasons.sort(key=lambda s: s.get("season_number", 1))
            for s_info in raw_seasons:
                s_num = s_info.get("season_number", 1)
                ep_cnt = s_info.get("episode_count", 0)
                ep_list = []
                for ep_idx in range(1, ep_cnt + 1):
                    db_sib = db_episodes.get((s_num, ep_idx))
                    ep_list.append({
                        "episode_number": ep_idx,
                        "name": f"Episode {ep_idx}",
                        "s": s_num,
                        "e": ep_idx,
                        "movie_id": db_sib["id"] if db_sib else movie_id,
                    })
                seasons.append({
                    "season_number": s_num,
                    "name": s_info.get("name") or f"Season {s_num}",
                    "episode_count": ep_cnt,
                    "episodes": ep_list,
                })

    # If TMDB had no seasons, build structure from database episodes
    if not seasons and db_episodes:
        grouped = {}
        for (s_num, e_num), sib in db_episodes.items():
            grouped.setdefault(s_num, []).append((e_num, sib))

        for s_num in sorted(grouped.keys()):
            ep_items = grouped[s_num]
            ep_items.sort(key=lambda x: x[0])
            ep_list = []
            for e_num, sib in ep_items:
                ep_list.append({
                    "episode_number": e_num,
                    "name": f"Episode {e_num}",
                    "s": s_num,
                    "e": e_num,
                    "movie_id": sib["id"],
                })
            seasons.append({
                "season_number": s_num,
                "name": f"Season {s_num}",
                "episode_count": len(ep_list),
                "episodes": ep_list,
            })

    # Guarantee that current_season is ALWAYS present in seasons for any series
    if is_series and current_season and not any(s["season_number"] == current_season for s in seasons):
        cur_season_eps = []
        for (s_num, e_num), sib in db_episodes.items():
            if s_num == current_season and re.search(r"\bEpisode\s*\d+", sib.get("title") or "", re.I):
                cur_season_eps.append((e_num, sib))

        ep_list = []
        if cur_season_eps:
            cur_season_eps.sort(key=lambda x: x[0])
            for e_num, sib in cur_season_eps:
                ep_list.append({
                    "episode_number": e_num,
                    "name": f"Episode {e_num}",
                    "s": current_season,
                    "e": e_num,
                    "movie_id": sib["id"],
                })
        else:
            # Check if title specifies an episode range (e.g. Episode 1-8)
            ep_match = re.search(r"\bEpisode\s*(\d+)(?:\s*-\s*(\d+))?\b", title, re.I)
            if ep_match and ep_match.group(2):
                start_ep = int(ep_match.group(1))
                end_ep = int(ep_match.group(2))
                for idx in range(start_ep, end_ep + 1):
                    ep_list.append({
                        "episode_number": idx,
                        "name": f"Episode {idx}",
                        "s": current_season,
                        "e": idx,
                        "movie_id": movie_id,
                    })
            else:
                prev_counts = [s["episode_count"] for s in seasons if s.get("episode_count")]
                fallback_count = prev_counts[-1] if prev_counts else max(current_episode, 8)
                fallback_count = max(fallback_count, current_episode, 8)
                for idx in range(1, fallback_count + 1):
                    ep_list.append({
                        "episode_number": idx,
                        "name": f"Episode {idx}",
                        "s": current_season,
                        "e": idx,
                        "movie_id": movie_id,
                    })

        seasons.append({
            "season_number": current_season,
            "name": f"Season {current_season}",
            "episode_count": len(ep_list),
            "episodes": ep_list,
        })
        seasons.sort(key=lambda s: s["season_number"])

    # Fallback single season for series with no sibling rows / no TMDB matches
    if not seasons and is_series:
        s_target = current_season or 1
        e_target = current_episode or 1
        seasons.append({
            "season_number": s_target,
            "name": f"Season {s_target}",
            "episode_count": 1,
            "episodes": [{
                "episode_number": e_target,
                "name": f"Episode {e_target}",
                "s": s_target,
                "e": e_target,
                "movie_id": movie_id,
            }],
        })

    return {
        "is_series": True,
        "title": clean_name or title,
        "current_season": current_season,
        "current_episode": current_episode,
        "seasons": seasons,
    }
