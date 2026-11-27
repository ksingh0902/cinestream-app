# app/api/routes_catalog.py
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..adapters import registry

router = APIRouter()

_FILTER_CACHE_TTL_SECONDS = 600.0  # 10 minutes cache per filter
_FILTER_CACHE_MAX_ENTRIES = 512
_filter_cache: dict[tuple, tuple[float, list[dict]]] = {}
_filter_cache_lock = threading.Lock()


def get_db_connection() -> sqlite3.Connection:
    """Open the catalogue read-only so web traffic can never lock a sync job."""
    target_path = os.getenv("DB_PATH") or ("yomovies.db" if os.path.exists("yomovies.db") else "cinemymovies.sqlite3")
    db_uri = Path(target_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(db_uri, uri=True, timeout=5, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA query_only=ON")
    # Keep per-worker SQLite memory modest on the 1 GB Oracle instance.
    conn.execute("PRAGMA cache_size = -8192")
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

_poster_fallbacks_map: dict[tuple[str, int], list[str]] | None = None
_poster_fallbacks_lock = threading.Lock()

_canonical_source_counts: dict[tuple[str, int], int] | None = None
_canonical_source_counts_lock = threading.Lock()

_poster_resolve_cache: dict[tuple[str, str, int], tuple[float, Optional[str]]] = {}
_poster_resolve_lock = threading.Lock()
_POSTER_RESOLVE_TTL = 86400.0
_POSTER_RESOLVE_MAX = 2048

_backdrop_resolve_cache: dict[tuple[str, str, int, str], tuple[float, Optional[str], str]] = {}
_backdrop_resolve_lock = threading.Lock()
_BACKDROP_RESOLVE_TTL = 86400.0
_BACKDROP_RESOLVE_MAX = 512


def _get_canonical_source_counts() -> dict[tuple[str, int], int]:
    """Cached map of canonical (normalized_title, is_series) -> number of distinct catalogue sources (1..4)."""
    global _canonical_source_counts
    with _canonical_source_counts_lock:
        if _canonical_source_counts is not None:
            return _canonical_source_counts
        grouped: dict[tuple[str, int], set[str]] = {}
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT title, is_series, source FROM movies WHERE title IS NOT NULL AND source IS NOT NULL"
            ).fetchall()
            for r in rows:
                nt = _normalized_title(r["title"])
                if not nt:
                    continue
                key = (nt, 1 if r["is_series"] else 0)
                grouped.setdefault(key, set()).add(str(r["source"]).lower())
        _canonical_source_counts = {k: len(v) for k, v in grouped.items()}
        return _canonical_source_counts


def get_canonical_source_count(title: str | None, is_series: int | bool | None) -> int:
    nt = _normalized_title(title)
    if not nt:
        return 1
    return _get_canonical_source_counts().get((nt, 1 if is_series else 0), 1)


def _clean_poster_lookup_title(title: str | None) -> str:
    """Clean noisy scraped title suffixes for TMDB poster lookup (e.g. 'Mastaney (2023) Punjabi' -> 'Mastaney')."""
    value = str(title or "").strip()
    value = re.sub(r"\s*[\[(]\s*(?:19|20)\d{2}\s*[\])]", " ", value)
    value = re.sub(r"\s*[\[(][^)\]]*(?:netflix|amazon|prime|hotstar|zee5|sonyliv|tvf|originals?|hindi|punjabi|dubbed)[^)\]]*[\])]", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:season\s*\d+|s\d+|episode\s*\d+|ep\s*\d+|part\s*\d+|vol\s*\d+)\b.*$", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:hindi dubbed|hollywood dubbed|dual[ -]?audio|english dubbed|punjabi|hindi|tamil|telugu|malayalam|watch online.*|full movie|web series)\b", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*[-–—|:]\s*$", " ", value)
    return re.sub(r"\s+", " ", value).strip()


@router.get("/api/poster/resolve")
def resolve_poster_fallback(
    title: str = Query(..., min_length=1, max_length=200),
    year: Optional[str] = Query(default=None, max_length=10),
    is_series: int = Query(default=0, ge=0, le=1),
):
    """
    Bounded, cached on-demand poster resolver called ONLY when a card's primary poster
    and DB mirror fallbacks fail to load in the browser. Zero DB writes, 24h in-memory cache.
    """
    clean_title = _clean_poster_lookup_title(title)
    if not clean_title:
        return {"poster_url": None, "source": "none"}

    clean_year = str(year or "").strip()
    if not (clean_year.isdigit() and len(clean_year) == 4):
        clean_year = ""

    cache_key = (clean_title.lower(), clean_year, int(is_series))
    now_mono = time.monotonic()
    with _poster_resolve_lock:
        cached = _poster_resolve_cache.get(cache_key)
        if cached and (now_mono - cached[0] < _POSTER_RESOLVE_TTL):
            return {"poster_url": cached[1], "source": "cache" if cached[1] else "none"}

    # 1. Check in-memory DB mirror map first (zero network)
    nt = _normalized_title(title)
    if nt:
        mirrors = _get_poster_fallbacks_map().get((nt, int(is_series))) or []
        for u in mirrors:
            if "image.tmdb.org" in u.lower() or "images.metahub.space" in u.lower():
                with _poster_resolve_lock:
                    _poster_resolve_cache[cache_key] = (now_mono, u)
                return {"poster_url": u, "source": "mirror"}

    # 2. Bounded single-shot IMDb suggestion lookup (fast CloudFront CDN, no ISP resets, works for regional/Punjabi too)
    resolved_url: Optional[str] = None
    resolved_src = "none"
    try:
        import urllib.parse
        import httpx

        first_ch = next((c for c in clean_title.lower() if c.isalnum()), "")
        if first_ch:
            slug = urllib.parse.quote(clean_title.lower().replace(" ", "_"))
            with httpx.Client(timeout=3.5, headers={"User-Agent": "Mozilla/5.0"}) as client:
                r = client.get(f"https://v3.sg.media-imdb.com/suggestion/{first_ch}/{slug}.json")
                if r.status_code == 200:
                    entries = r.json().get("d") or []
                    # Prefer exact title (tt*) matches matching year when provided
                    best_url: Optional[str] = None
                    fallback_tt_url: Optional[str] = None
                    for item in entries:
                        iid = str(item.get("id") or "")
                        if not iid.startswith("tt"):
                            continue
                        img_url = str((item.get("i") or {}).get("imageUrl") or "").strip()
                        if not img_url.startswith("http"):
                            continue
                        # Resize large Amazon master image to lightweight poster (~380px wide)
                        if "m.media-amazon.com" in img_url and img_url.endswith("._V1_.jpg"):
                            img_url = img_url[:-9] + "._V1_QL75_UX380_.jpg"
                        item_year = str(item.get("y") or "").strip()
                        if clean_year and item_year == clean_year:
                            best_url = img_url
                            break
                        if not fallback_tt_url:
                            fallback_tt_url = img_url
                    resolved_url = best_url or fallback_tt_url
                    if resolved_url:
                        resolved_src = "imdb"
    except Exception:
        resolved_url = None

    # 3. Fallback to TMDB if IMDb suggestion did not yield a poster
    if not resolved_url:
        try:
            import httpx
            from ..adapters.embed_helper import TMDB_API_KEY

            api_key = os.getenv("TMDB_API_KEY") or TMDB_API_KEY
            if api_key:
                media = "tv" if is_series else "movie"
                params: dict[str, str] = {"api_key": api_key, "query": clean_title}
                if clean_year:
                    params["first_air_date_year" if is_series else "year"] = clean_year

                with httpx.Client(timeout=3.5) as client:
                    resp = client.get(f"https://api.themoviedb.org/3/search/{media}", params=params)
                    results = resp.json().get("results", []) if resp.status_code == 200 else []
                    if not results and clean_year:
                        params.pop("first_air_date_year", None)
                        params.pop("year", None)
                        resp = client.get(f"https://api.themoviedb.org/3/search/{media}", params=params)
                        results = resp.json().get("results", []) if resp.status_code == 200 else []
                    if not results:
                        resp = client.get(
                            "https://api.themoviedb.org/3/search/multi",
                            params={"api_key": api_key, "query": clean_title},
                        )
                        results = resp.json().get("results", []) if resp.status_code == 200 else []

                    for item in results:
                        pp = item.get("poster_path")
                        if pp and isinstance(pp, str):
                            resolved_url = f"https://image.tmdb.org/t/p/w500{pp}"
                            resolved_src = "tmdb"
                            break
        except Exception:
            resolved_url = None

    with _poster_resolve_lock:
        if len(_poster_resolve_cache) >= _POSTER_RESOLVE_MAX:
            oldest = min(_poster_resolve_cache, key=lambda k: _poster_resolve_cache[k][0])
            _poster_resolve_cache.pop(oldest, None)
        _poster_resolve_cache[cache_key] = (now_mono, resolved_url)

    return {"poster_url": resolved_url, "source": resolved_src}


@router.get("/api/backdrop/resolve")
def resolve_backdrop(
    title: str = Query(..., min_length=1, max_length=200),
    year: Optional[str] = Query(default=None, max_length=10),
    is_series: int = Query(default=0, ge=0, le=1),
    tmdb_id: Optional[str] = Query(default=None, max_length=20),
):
    """
    Bounded, cached on-demand widescreen HD backdrop resolver for Hero Spotlight banners.
    Returns official 16:9 TMDb w1280 backdrops (or HD poster fallback) with 24h in-memory cache.
    Zero DB writes.
    """
    clean_title = _clean_poster_lookup_title(title)
    clean_tmdb = str(tmdb_id or "").strip()
    if not clean_tmdb.isdigit():
        clean_tmdb = ""

    if not clean_title and not clean_tmdb:
        return {"backdrop_url": None, "source": "none"}

    clean_year = str(year or "").strip()
    if not (clean_year.isdigit() and len(clean_year) == 4):
        clean_year = ""

    cache_key = (clean_title.lower(), clean_year, int(is_series), clean_tmdb)
    now_mono = time.monotonic()
    with _backdrop_resolve_lock:
        cached = _backdrop_resolve_cache.get(cache_key)
        if cached:
            ttl = _BACKDROP_RESOLVE_TTL if cached[1] else 60.0
            if now_mono - cached[0] < ttl:
                return {"backdrop_url": cached[1], "source": "cache" if cached[1] else "none"}

    resolved_url: Optional[str] = None
    resolved_src = "none"
    try:
        import httpx
        from ..adapters.embed_helper import TMDB_API_KEY

        api_key = os.getenv("TMDB_API_KEY") or TMDB_API_KEY
        if api_key:
            media = "tv" if is_series else "movie"

            def _tmdb_get(client: httpx.Client, path: str, params: dict[str, str]):
                for host in ("https://api.themoviedb.org", "https://api.tmdb.org"):
                    try:
                        r = client.get(f"{host}{path}", params=params)
                        if r.status_code == 200:
                            return r.json() or {}
                    except Exception:
                        continue
                return {}

            with httpx.Client(timeout=4.0) as client:
                # 1. Direct TMDb ID lookup when available
                if clean_tmdb:
                    data = _tmdb_get(client, f"/3/{media}/{clean_tmdb}", {"api_key": api_key})
                    bp = data.get("backdrop_path")
                    pp = data.get("poster_path")
                    if bp and isinstance(bp, str):
                        resolved_url = f"https://image.tmdb.org/t/p/w1280{bp}"
                        resolved_src = "tmdb_backdrop"
                    elif pp and isinstance(pp, str):
                        resolved_url = f"https://image.tmdb.org/t/p/original{pp}"
                        resolved_src = "tmdb_poster_hd"

                # 2. Search TMDb by cleaned title + optional year
                if not resolved_url and clean_title:
                    params: dict[str, str] = {"api_key": api_key, "query": clean_title}
                    if clean_year:
                        params["first_air_date_year" if is_series else "year"] = clean_year

                    results = _tmdb_get(client, f"/3/search/{media}", params).get("results", [])
                    if not results and clean_year:
                        params.pop("first_air_date_year", None)
                        params.pop("year", None)
                        results = _tmdb_get(client, f"/3/search/{media}", params).get("results", [])
                    if not results:
                        results = _tmdb_get(
                            client,
                            "/3/search/multi",
                            {"api_key": api_key, "query": clean_title},
                        ).get("results", [])

                    # Prefer a result with a true widescreen backdrop_path
                    fallback_poster_path: Optional[str] = None
                    for item in results:
                        bp = item.get("backdrop_path")
                        if bp and isinstance(bp, str):
                            resolved_url = f"https://image.tmdb.org/t/p/w1280{bp}"
                            resolved_src = "tmdb_backdrop"
                            break
                        if not fallback_poster_path:
                            pp = item.get("poster_path")
                            if pp and isinstance(pp, str):
                                fallback_poster_path = pp
                    if not resolved_url and fallback_poster_path:
                        resolved_url = f"https://image.tmdb.org/t/p/original{fallback_poster_path}"
                        resolved_src = "tmdb_poster_hd"
    except Exception:
        resolved_url = None
        resolved_src = "none"

    with _backdrop_resolve_lock:
        if len(_backdrop_resolve_cache) >= _BACKDROP_RESOLVE_MAX:
            oldest = min(_backdrop_resolve_cache, key=lambda k: _backdrop_resolve_cache[k][0])
            _backdrop_resolve_cache.pop(oldest, None)
        _backdrop_resolve_cache[cache_key] = (now_mono, resolved_url, resolved_src)

    return {"backdrop_url": resolved_url, "source": resolved_src}


def _is_valid_poster_url(val: str | None) -> bool:
    s = str(val or "").strip()
    if not s or s in ("None", "null") or "logo.png" in s or s.startswith("/assets/"):
        return False
    return s.startswith("http://") or s.startswith("https://")


def _poster_host_priority(url: str) -> int:
    low = url.lower()
    if "image.tmdb.org" in low:
        return 0
    if "images.metahub.space" in low:
        return 1
    if "m.media-amazon.com" in low and "xkeyxkfqcgc@" in low:
        return 2
    if "m.media-amazon.com" in low and "xkeyxkfqcgde" in low:
        return 4
    return 3


def _get_poster_fallbacks_map() -> dict[tuple[str, int], list[str]]:
    """Build a lightweight in-memory map of alternative valid poster URLs per canonical (title, is_series)."""
    global _poster_fallbacks_map
    with _poster_fallbacks_lock:
        if _poster_fallbacks_map is not None:
            return _poster_fallbacks_map
        grouped: dict[tuple[str, int], set[str]] = {}
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT title, is_series, poster, poster_url FROM movies WHERE title IS NOT NULL AND (COALESCE(poster, poster_url, '') != '')"
            ).fetchall()
            for r in rows:
                nt = _normalized_title(r["title"])
                if not nt:
                    continue
                key = (nt, 1 if r["is_series"] else 0)
                for col in ("poster", "poster_url"):
                    u = str(r[col] or "").strip()
                    if _is_valid_poster_url(u):
                        grouped.setdefault(key, set()).add(u)
        compiled: dict[tuple[str, int], list[str]] = {}
        for k, urls in grouped.items():
            if len(urls) > 1:
                compiled[k] = sorted(urls, key=lambda u: (_poster_host_priority(u), u))[:4]
        _poster_fallbacks_map = compiled
        return _poster_fallbacks_map


def _get_fallback_posters(title: str | None, is_series: int | bool | None, exclude_url: str | None) -> list[str]:
    nt = _normalized_title(title)
    if not nt:
        return []
    key = (nt, 1 if is_series else 0)
    urls = _get_poster_fallbacks_map().get(key)
    if not urls:
        return []
    ex = str(exclude_url or "").strip()
    return [u for u in urls if u != ex][:3]


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
    global _non_m7_title_keys, _non_m7_base_titles, _poster_fallbacks_map, _canonical_source_counts
    with _filter_cache_lock:
        _filter_cache.clear()
    with _non_m7_title_keys_lock:
        _non_m7_title_keys = None
        _non_m7_base_titles = None
    with _poster_fallbacks_lock:
        _poster_fallbacks_map = None
    with _canonical_source_counts_lock:
        _canonical_source_counts = None
    try:
        from ..discovery import invalidate_discovery_cache
        invalidate_discovery_cache()
    except Exception:
        pass


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


def _recently_added_year_int(item: dict) -> int:
    raw = str(item.get("year") or "").strip()
    if raw.isdigit() and len(raw) == 4:
        return int(raw)
    return 0


def _recently_added_rank_key(item: dict) -> tuple[int, int, int]:
    """Existing Recently Added ranking within a source: verified release year DESC, first_added_at DESC, id DESC."""
    ts = int(item.get("first_added_at") or item.get("updated_at") or 0)
    return (-_recently_added_year_int(item), -ts, -int(item.get("id") or 0))


def _apply_recently_added_source_priority(items: list[dict], yomovies_slots: int = 10) -> list[dict]:
    """
    Canonical-title deduplication + source priority for Recently Added:
    - Deduplicate by canonical normalized title (preferring yomovies when a title exists on multiple sources).
    - Positions 1..yomovies_slots (default 10): eligible titles whose canonical source is 'yomovies',
      ordered by existing Recently Added ranking (release year DESC, first_added_at DESC, id DESC).
    - Positions 11+: eligible titles from other sources (dooflix, ask4movie, movies7, etc.) interleaved
      by existing per-source Recently Added ranking, followed by any remaining yomovies titles if other
      sources are exhausted.
    - If fewer than 10 eligible yomovies titles exist, fills remaining slots from other sources with no gaps.
    """
    groups: dict[str, list[dict]] = {}
    for item in items:
        nt = _normalized_title(item.get("title"))
        key = nt if nt else f"id:{item.get('id')}"
        groups.setdefault(key, []).append(item)

    canonical_items: list[dict] = []
    for candidates in groups.values():
        candidates.sort(
            key=lambda row: (
                _source_priority((row.get("source") or "").lower()),
                _recently_added_rank_key(row),
            )
        )
        primary = candidates[0]
        primary["audio_edition"] = _audio_edition(primary)
        primary["available_source_count"] = len({(row.get("source") or "").lower() for row in candidates if row.get("source")})
        canonical_items.append(primary)

    yomovies_items = [
        item for item in canonical_items if (item.get("source") or "").lower() == "yomovies"
    ]
    yomovies_items.sort(key=_recently_added_rank_key)

    other_by_source: dict[str, list[dict]] = {}
    for item in canonical_items:
        src = (item.get("source") or "").lower()
        if src == "yomovies":
            continue
        other_by_source.setdefault(src, []).append(item)

    for src_items in other_by_source.values():
        src_items.sort(key=_recently_added_rank_key)

    ordered_other_sources = sorted(
        other_by_source.keys(),
        key=lambda s: (_source_priority(s), s),
    )
    interleaved_others: list[dict] = []
    if ordered_other_sources:
        max_len = max(len(other_by_source[s]) for s in ordered_other_sources)
        for idx in range(max_len):
            for src in ordered_other_sources:
                bucket = other_by_source[src]
                if idx < len(bucket):
                    interleaved_others.append(bucket[idx])

    top_yomovies = yomovies_items[:yomovies_slots]
    remaining_yomovies = yomovies_items[yomovies_slots:]
    return top_yomovies + interleaved_others + remaining_yomovies


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
    fallbacks = _get_fallback_posters(d.get("title"), d.get("is_series"), d.get("poster"))
    if fallbacks:
        d["poster_fallbacks"] = fallbacks
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

    if d.get("latest_quality_transition"):
        d["upgradeBadge"] = d["latest_quality_transition"]

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
    quality: Optional[str] = None,
    language: Optional[str] = None,
    window_months: Optional[int] = None,
    page: int = 1,
    per_page: int = 48,
):
    page = max(1, int(page))
    per_page = min(100, max(1, int(per_page)))
    filter_key = (
        source or "",
        (q or "").strip().lower(),
        (genre or "").strip().lower(),
        year or "",
        series,
        sort,
        page,
        per_page,
        (quality or "").strip().lower(),
        (language or "").strip().lower(),
        window_months or 0,
    )
    now = time.monotonic()

    # Instant memory cache check (0.01ms)
    with _filter_cache_lock:
        cached = _filter_cache.get(filter_key)
        if cached and (now - cached[0] < _FILTER_CACHE_TTL_SECONDS):
            return cached[1]

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
        if year.lower() == "older":
            where.append("year GLOB '[12][09][0-9][0-9]' AND CAST(year AS INT) < 2020")
        else:
            where.append("year = ?")
            args.append(year)

    if quality:
        where.append("quality LIKE ?")
        args.append(f"%{quality}%")

    if language:
        where.append("(language LIKE ? OR language_code LIKE ? OR title LIKE ? OR genres LIKE ?)")
        args.extend([f"%{language}%", f"%{language[:2]}%", f"%{language}%", f"%{language}%"])

    if window_months and int(window_months) > 0:
        cutoff_ts = int(time.time()) - (int(window_months) * 30 * 86400)
        if sort == "recently_upgraded":
            where.append("last_quality_upgrade_at >= ?")
            args.append(cutoff_ts)
        elif sort in ("first_added", "newest_added"):
            where.append("COALESCE(first_added_at, updated_at, 0) >= ?")
            args.append(cutoff_ts)

    if sort == "recently_upgraded":
        where.append("last_quality_upgrade_at IS NOT NULL")

    where_clause = " AND ".join(where)

    # Ordering:
    if q_str:
        order = "CASE WHEN title LIKE ? THEN 0 WHEN title LIKE ? THEN 1 ELSE 2 END, CAST(year AS INT) DESC, id ASC"
        query_sql = f"SELECT * FROM movies WHERE {where_clause} ORDER BY {order}"
        query_args = args + [f"{q_str}%", f"%{q_str}%"]
    elif sort in ("first_added", "newest_added"):
        query_sql = f"""
            WITH filtered AS (
                SELECT * FROM movies WHERE {where_clause}
            ),
            ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY source 
                    ORDER BY 
                        CAST(COALESCE(NULLIF(year, ''), '0') AS INT) DESC, 
                        COALESCE(first_added_at, updated_at, 0) DESC,
                        id ASC
                ) AS src_rank
                FROM filtered
            )
            SELECT * FROM ranked 
            ORDER BY src_rank ASC, 
                CASE source 
                    WHEN 'yomovies' THEN 1 
                    WHEN 'dooflix' THEN 2 
                    WHEN 'ask4movie' THEN 3 
                    ELSE 4 
                END ASC
        """
        query_args = args
    elif sort == "recently_upgraded":
        query_sql = f"SELECT * FROM movies WHERE {where_clause} ORDER BY last_quality_upgrade_at DESC, id DESC"
        query_args = args
    elif sort == "year":
        query_sql = f"SELECT * FROM movies WHERE {where_clause} ORDER BY CAST(COALESCE(NULLIF(year, ''), '0') AS INT) DESC, id ASC"
        query_args = args
    elif sort == "quality":
        query_sql = f"""
            SELECT * FROM movies WHERE {where_clause}
            ORDER BY 
                CASE 
                    WHEN quality LIKE '%4K%' OR quality LIKE '%2160%' THEN 50
                    WHEN quality LIKE '%BluRay%' OR quality LIKE '%BDRip%' THEN 40
                    WHEN quality LIKE '%1080%' OR quality LIKE '%FHD%' OR quality LIKE '%WEB-DL%' OR quality LIKE '%WEBRip%' THEN 30
                    WHEN quality LIKE '%720%' OR quality LIKE '%HD%' THEN 20
                    WHEN quality LIKE '%DVD%' OR quality LIKE '%SD%' THEN 10
                    ELSE 0
                END DESC,
                CAST(COALESCE(NULLIF(year, ''), '0') AS INT) DESC,
                id ASC
        """
        query_args = args
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

    # Do not materialise a 30k+ row result just to render the first page.  The
    # extra room preserves source/edition grouping while keeping VM work bounded.
    is_recently_added_sort = sort in ("first_added", "newest_added") and not q_str
    if is_recently_added_sort:
        candidate_limit = min(4000, max(1200, page * per_page * 6))
    else:
        candidate_limit = min(1000, max(192, page * per_page * 8))
    query_sql += " LIMIT ?"
    query_args = list(query_args) + [candidate_limit]

    with get_db_connection() as conn:
        raw_rows = conn.execute(query_sql, query_args).fetchall()
        raw_total = conn.execute(
            f"SELECT COUNT(*) FROM movies WHERE {where_clause}", args
        ).fetchone()[0]
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
            if is_recently_added_sort:
                items_list = _apply_recently_added_source_priority(formatted, yomovies_slots=10)
            else:
                items_list = _group_ordered_editions(formatted)

    offset = (page - 1) * per_page
    exhausted = len(raw_rows) < candidate_limit
    result = {
        # Exact canonical count when all rows were evaluated; otherwise raw_total.
        "total": len(items_list) if exhausted else raw_total,
        "page": page,
        "per_page": per_page,
        "items": items_list[offset:offset + per_page],
        "has_more": len(items_list) > offset + per_page,
    }

    with _filter_cache_lock:
        if len(_filter_cache) >= _FILTER_CACHE_MAX_ENTRIES:
            oldest_key = min(_filter_cache, key=lambda k: _filter_cache[k][0])
            _filter_cache.pop(oldest_key, None)
        _filter_cache[filter_key] = (now, result)

    return result


DEFAULT_HOMEPAGE_PREFERENCES = {
    "recently_added_enabled": True,
    "recently_upgraded_enabled": True,
    "recently_added_window_months": 3,
    "recently_upgraded_window_months": 3,
    "default_sort": "recent",
    "allowed_qualities": ["4K", "1080p", "720p", "HD", "WEB-DL", "BluRay"],
}


@router.get("/api/catalog/recently-added")
def recently_added(
    limit: int = 24,
    window_months: int = 3,
    series: Optional[int] = None,
    latest_crawl: bool = False,
):
    """
    Discovery row: Titles first discovered within the configured time window (default 3 months).
    When latest_crawl=True, restricts to the most recent crawler run (24h around latest timestamp).
    Sorted newest first using original first_added_at, de-duplicated by title.
    """
    limit = min(100, max(1, int(limit)))
    window = max(1, min(24, int(window_months)))
    window_cutoff_ts = int(time.time()) - (window * 30 * 86400)
    cutoff_ts = window_cutoff_ts

    if latest_crawl:
        with get_db_connection() as conn:
            max_ts = conn.execute("SELECT MAX(COALESCE(first_added_at, updated_at, 0)) FROM movies").fetchone()[0] or 0
        if max_ts > 0:
            cutoff_ts = max(cutoff_ts, int(max_ts) - 86400)

    base_where = [
        "title IS NOT NULL AND title != ''",
        f"({ADULT_EXCLUSION_SQL})",
        "(COALESCE(poster, poster_url, '') != '' AND poster NOT LIKE '%logo.png%')",
    ]
    base_args: list = []

    if series is not None:
        base_where.append("is_series = ?")
        base_args.append(series)

    where = list(base_where) + ["COALESCE(first_added_at, updated_at, 0) >= ?"]
    args: list = list(base_args) + [cutoff_ts]

    where_clause = " AND ".join(where)
    query_sql = f"""
        WITH filtered AS (
            SELECT * FROM movies WHERE {where_clause}
        ),
        ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY source 
                ORDER BY 
                    CAST(COALESCE(NULLIF(year, ''), '0') AS INT) DESC,
                    COALESCE(first_added_at, updated_at, 0) DESC,
                    id DESC
            ) AS src_rank
            FROM filtered
        )
        SELECT * FROM ranked 
        ORDER BY src_rank ASC, 
            CASE source 
                WHEN 'yomovies' THEN 1 
                WHEN 'dooflix' THEN 2 
                WHEN 'ask4movie' THEN 3 
                ELSE 4 
            END ASC
        LIMIT ?
    """
    fetch_limit = max(160, limit * 4)
    with get_db_connection() as conn:
        raw_rows = conn.execute(query_sql, args + [fetch_limit]).fetchall()
        candidates = []
        for r in raw_rows:
            d = dict(r)
            if d.get("source") == "movies7" and is_movie_available_on_primary_sources(d.get("title"), d.get("year")):
                continue
            candidates.append(_format_row(d))

        # When latest_crawl=True and the most recent 24h crawl had zero new yomovies titles,
        # top up the 10 YoMovies priority slots from YoMovies' most recent crawl within window_months.
        if latest_crawl and cutoff_ts > window_cutoff_ts:
            ym_count = sum(1 for c in candidates if (c.get("source") or "").lower() == "yomovies")
            if ym_count == 0:
                ym_where = list(base_where) + [
                    "source = 'yomovies'",
                    "COALESCE(first_added_at, updated_at, 0) >= ?",
                ]
                ym_sql = f"""
                    SELECT * FROM movies
                    WHERE {' AND '.join(ym_where)}
                    ORDER BY
                        CAST(COALESCE(NULLIF(year, ''), '0') AS INT) DESC,
                        COALESCE(first_added_at, updated_at, 0) DESC,
                        id DESC
                    LIMIT 10
                """
                ym_rows = conn.execute(ym_sql, list(base_args) + [window_cutoff_ts]).fetchall()
                existing_ids = {c.get("id") for c in candidates}
                for r in ym_rows:
                    d = dict(r)
                    if d.get("id") not in existing_ids:
                        candidates.append(_format_row(d))
                        existing_ids.add(d.get("id"))

    prioritized = _apply_recently_added_source_priority(candidates, yomovies_slots=10)
    formatted = prioritized[:limit]

    # Pre-attach crisp 16:9 TMDb w1280 backdrops on the top 6 hero spotlight items (parallel, 24h cached)
    hero_slice = formatted[:6]
    if hero_slice:
        from concurrent.futures import ThreadPoolExecutor

        def _attach_backdrop(item: dict) -> None:
            if item.get("backdrop_url") or item.get("backdrop"):
                return
            try:
                res = resolve_backdrop(
                    title=str(item.get("title") or ""),
                    year=str(item.get("year") or "") or None,
                    is_series=1 if item.get("is_series") else 0,
                    tmdb_id=str(item.get("tmdb_id") or "") or None,
                )
                bd = res.get("backdrop_url") if isinstance(res, dict) else None
                if bd:
                    item["backdrop_url"] = bd
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=min(6, len(hero_slice))) as pool:
            list(pool.map(_attach_backdrop, hero_slice))

    return {
        "total": len(formatted),
        "items": formatted,
        "window_months": window,
    }


@router.get("/api/catalog/recently-upgraded")
def recently_upgraded(limit: int = 24, window_months: int = 3, series: Optional[int] = None):
    """
    Discovery row: Titles with a verified quality improvement within the configured time window.
    Sorted by most recent verified upgrade first, containing upgrade badge (e.g. CAM → HD).
    """
    limit = min(60, max(1, int(limit)))
    window = max(1, min(24, int(window_months)))
    cutoff_ts = int(time.time()) - (window * 30 * 86400)

    where = [
        "title IS NOT NULL AND title != ''",
        f"({ADULT_EXCLUSION_SQL})",
        "(COALESCE(poster, poster_url, '') != '' AND poster NOT LIKE '%logo.png%')",
        "last_quality_upgrade_at IS NOT NULL",
        "last_quality_upgrade_at >= ?",
    ]
    args: list = [cutoff_ts]

    if series is not None:
        where.append("is_series = ?")
        args.append(series)

    where_clause = " AND ".join(where)
    query_sql = f"""
        SELECT * FROM movies
        WHERE {where_clause}
        ORDER BY last_quality_upgrade_at DESC, id DESC
        LIMIT ?
    """
    with get_db_connection() as conn:
        raw_rows = conn.execute(query_sql, args + [limit * 2]).fetchall()
        formatted = []
        seen_titles = set()
        for r in raw_rows:
            d = dict(r)
            nt = _normalized_title(d.get("title"))
            if nt in seen_titles:
                continue
            seen_titles.add(nt)
            formatted.append(_format_row(d))
            if len(formatted) >= limit:
                break

    return {
        "total": len(formatted),
        "items": formatted,
        "window_months": window,
    }


@router.get("/api/catalog/years")
def catalog_years():
    """
    Release year navigation metadata: Returns actual catalogue release years and title counts.
    """
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT year, COUNT(*) as cnt
            FROM movies
            WHERE year GLOB '[12][09][0-9][0-9]'
            GROUP BY year
            ORDER BY CAST(year AS INT) DESC
        """).fetchall()
        years_list = [{"year": str(r["year"]), "count": int(r["cnt"])} for r in rows]
        older_cnt = conn.execute("""
            SELECT COUNT(*) FROM movies
            WHERE year GLOB '[12][09][0-9][0-9]' AND CAST(year AS INT) < 2020
        """).fetchone()[0]

    return {
        "years": years_list,
        "older_count": older_cnt,
    }


@router.get("/api/homepage/preferences")
def get_homepage_preferences():
    """
    Retrieve active homepage discovery preferences.
    """
    try:
        from ..auth.store import get_meta_value
        val = get_meta_value("homepage_preferences")
        if val:
            return {**DEFAULT_HOMEPAGE_PREFERENCES, **json.loads(val)}
    except Exception:
        pass
    return DEFAULT_HOMEPAGE_PREFERENCES


@router.post("/api/admin/homepage/preferences")
def update_homepage_preferences(prefs: dict):
    """
    Admin-only configuration for homepage discovery sections.
    """
    try:
        from ..auth.store import get_db_connection as get_auth_conn, set_meta_value
        clean_prefs = {**DEFAULT_HOMEPAGE_PREFERENCES}
        if "recently_added_enabled" in prefs:
            clean_prefs["recently_added_enabled"] = bool(prefs["recently_added_enabled"])
        if "recently_upgraded_enabled" in prefs:
            clean_prefs["recently_upgraded_enabled"] = bool(prefs["recently_upgraded_enabled"])
        if "recently_added_window_months" in prefs:
            clean_prefs["recently_added_window_months"] = max(1, min(12, int(prefs["recently_added_window_months"])))
        if "recently_upgraded_window_months" in prefs:
            clean_prefs["recently_upgraded_window_months"] = max(1, min(12, int(prefs["recently_upgraded_window_months"])))
        if "default_sort" in prefs:
            clean_prefs["default_sort"] = str(prefs["default_sort"])
        if "allowed_qualities" in prefs and isinstance(prefs["allowed_qualities"], list):
            clean_prefs["allowed_qualities"] = [str(q) for q in prefs["allowed_qualities"]]

        with get_auth_conn() as conn:
            set_meta_value(conn, "homepage_preferences", json.dumps(clean_prefs))
            conn.commit()
        return {"ok": True, "preferences": clean_prefs}
    except Exception as exc:
        raise HTTPException(500, f"Failed to save preferences: {exc}")


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
            if not tmdb_id and sib["tmdb_id"]:
                tmdb_id = sib["tmdb_id"]
            s_m = re.search(r"\bSeason\s*(\d+)\b", sib["title"] or "", re.I)
            e_m = re.search(r"\bEpisode\s*(\d+)\b", sib["title"] or "", re.I)
            if s_m and e_m:
                s_num = int(s_m.group(1))
                e_num = int(e_m.group(1))
                if (s_num, e_num) not in db_episodes or sib["source"] == row["source"]:
                    db_episodes[(s_num, e_num)] = dict(sib)
            elif sib["id"] == movie_id:
                db_episodes[(1, 1)] = dict(sib)

    if not tmdb_id:
        # Production catalogue storage is read-only. A later laptop sync can
        # persist this enrichment; serving a season must never lock the DB.
        tmdb_id = _lookup_tmdb_tv_id(clean_name, str(row["year"] or ""))

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
