from __future__ import annotations

import json
import logging
from typing import Iterator, Optional

import httpx

from ..base import MediaItem
from .config import CFG

logger = logging.getLogger("movies7.catalog")

GENRE_MAP: dict[int, str] = {
    28: "Action",
    12: "Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    14: "Fantasy",
    36: "History",
    27: "Horror",
    10402: "Music",
    9648: "Mystery",
    10749: "Romance",
    878: "Sci-Fi",
    10770: "TV Movie",
    53: "Thriller",
    10752: "War",
    37: "Western",
    10759: "Action & Adventure",
    10762: "Kids",
    10763: "News",
    10764: "Reality",
    10765: "Sci-Fi & Fantasy",
    10766: "Soap",
    10767: "Talk",
    10768: "War & Politics",
}

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "pa": "Punjabi",
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "kn": "Kannada",
    "ko": "Korean",
    "ja": "Japanese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "zh": "Chinese",
}


def _get_client() -> httpx.Client:
    return httpx.Client(
        timeout=CFG.timeout_s,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": CFG.origin,
        },
    )


def fetch_tmdb_endpoint(endpoint: str, page: int = 1, client: Optional[httpx.Client] = None) -> dict:
    """Query TMDB endpoint trying keys/hosts with fallback."""
    local_client = client or _get_client()
    try:
        for host in CFG.tmdb_hosts:
            for key in CFG.tmdb_keys:
                try:
                    url = f"https://{host}/3/{endpoint}"
                    resp = local_client.get(url, params={"api_key": key, "page": page, "language": "en-US"})
                    if resp.status_code == 200:
                        return resp.json()
                except Exception:
                    continue
    finally:
        if client is None:
            local_client.close()
    return {}


def normalize_item(raw: dict, is_series: bool = False) -> Optional[MediaItem]:
    """Convert raw TMDB item into MediaItem."""
    tmdb_id = raw.get("id")
    if not tmdb_id:
        return None

    title = raw.get("title") or raw.get("name") or raw.get("original_title") or raw.get("original_name")
    if not title:
        return None

    date_str = raw.get("release_date") or raw.get("first_air_date") or ""
    year = None
    if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
        year = int(date_str[:4])

    orig_lang = raw.get("original_language") or "en"
    lang_name = LANGUAGE_NAMES.get(orig_lang, orig_lang.upper())

    poster_path = raw.get("poster_path")
    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

    vote_avg = raw.get("vote_average")
    rating = round(float(vote_avg), 1) if vote_avg is not None else None

    genre_ids = raw.get("genre_ids") or []
    genre_names = [GENRE_MAP[gid] for gid in genre_ids if gid in GENRE_MAP]
    genres_json = json.dumps(genre_names)

    synopsis = raw.get("overview") or ""

    type_prefix = "tv" if is_series else "movie"
    source_id = f"m7-{type_prefix}-{tmdb_id}"
    detail_url = f"https://movies7to.net/watch/{type_prefix}/{tmdb_id}"

    return MediaItem(
        source="movies7",
        source_id=source_id,
        title=title,
        year=year,
        language=lang_name,
        language_code=orig_lang,
        poster_url=poster_url,
        duration_s=None,
        rating=rating,
        genres=genres_json,
        synopsis=synopsis,
        tmdb_id=int(tmdb_id),
        is_series=is_series,
        detail_url=detail_url,
        player_kind="iframe",
    )


def iter_catalog(*, max_pages: int = 0) -> Iterator[MediaItem]:
    """Yield MediaItems from Movies7 endpoints (movies and webseries)."""
    endpoints = [
        ("movie/popular", False),
        ("tv/popular", True),
        ("movie/top_rated", False),
        ("tv/top_rated", True),
        ("movie/now_playing", False),
        ("tv/on_the_air", True),
        ("trending/movie/week", False),
        ("trending/tv/week", True),
    ]

    pages_per_endpoint = max_pages if max_pages > 0 else 5
    client = _get_client()

    seen_ids = set()

    try:
        for ep, is_series in endpoints:
            for p in range(1, pages_per_endpoint + 1):
                data = fetch_tmdb_endpoint(ep, page=p, client=client)
                results = data.get("results") or []
                if not results:
                    break
                for item_raw in results:
                    item_id = item_raw.get("id")
                    dedup_key = (item_id, is_series)
                    if dedup_key in seen_ids:
                        continue
                    seen_ids.add(dedup_key)

                    media_item = normalize_item(item_raw, is_series=is_series)
                    if media_item:
                        yield media_item
    finally:
        client.close()
