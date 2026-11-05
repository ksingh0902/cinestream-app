from __future__ import annotations

import re
from typing import Optional

from ..base import StreamInfo
from .config import CFG


def resolve(
    detail_url: str,
    *,
    tmdb_id: Optional[int | str] = None,
    is_series: bool = False,
    season: Optional[int | str] = None,
    episode: Optional[int | str] = None,
) -> StreamInfo:
    """Resolve playback servers for Movies7 items.
    Generates multi-source embeds (Videasy, Vsembed, 111Movies, PrimeSrc)
    matching movies7to.net's player stack.
    """
    tid = str(tmdb_id) if tmdb_id else None
    series_detected = is_series

    if not tid and detail_url:
        m = re.search(r"/(?:tv|movie|watch)/(\d+)", detail_url)
        if m:
            tid = m.group(1)
        if "/tv/" in detail_url:
            series_detected = True

    if not tid:
        # Fallback if URL is generic
        m_any = re.search(r"(\d{3,9})", detail_url or "")
        if m_any:
            tid = m_any.group(1)

    s = str(season or 1)
    e = str(episode or 1)

    if series_detected:
        primary_url = f"https://embed.filmu.in/tv/{tid}/{s}/{e}"
        servers = [
            {"label": "Server 1 (FilmU - Fast HD)", "url": f"https://embed.filmu.in/tv/{tid}/{s}/{e}"},
            {"label": "Server 2 (VIP - No ADS)", "url": f"https://embed.vidsrc.si/embed/tv/{tid}/{s}/{e}?autoplay=1&ds_lang=en"},
            {"label": "Server 3 (Cinesrc - HD)", "url": f"https://cinesrc.st/embed/tv/{tid}/{s}/{e}"},
            {"label": "Server 4 (111Movies - Multi)", "url": f"https://111movies.net/tv/{tid}/{s}/{e}"},
            {"label": "Server 5 (VidLink - Fast HD)", "url": f"https://vidlink.pro/tv/{tid}/{s}/{e}"},
            {"label": "Server 6 (2Embed - Multi)", "url": f"https://www.2embed.cc/embedtv/{tid}&s={s}&e={e}"},
            {"label": "Server 7 (PrimeSrc - Stream)", "url": f"https://primesrc.me/embed/tv?tmdb={tid}&season={s}&episode={e}"},
        ]
    else:
        primary_url = f"https://embed.filmu.in/movie/{tid}"
        servers = [
            {"label": "Server 1 (FilmU - Fast HD)", "url": f"https://embed.filmu.in/movie/{tid}"},
            {"label": "Server 2 (VIP - No ADS)", "url": f"https://embed.vidsrc.si/embed/movie/{tid}?autoplay=1&ds_lang=en"},
            {"label": "Server 3 (Cinesrc - HD)", "url": f"https://cinesrc.st/embed/movie/{tid}"},
            {"label": "Server 4 (111Movies - Multi)", "url": f"https://111movies.net/movie/{tid}"},
            {"label": "Server 5 (VidLink - Fast HD)", "url": f"https://vidlink.pro/movie/{tid}"},
            {"label": "Server 6 (2Embed - Multi)", "url": f"https://www.2embed.cc/embed/{tid}"},
            {"label": "Server 7 (PrimeSrc - Stream)", "url": f"https://primesrc.me/embed/movie?tmdb={tid}"},
        ]

    return StreamInfo(
        kind="iframe",
        url=primary_url,
        servers=servers,
        headers={"Referer": "https://movies7to.net/"},
        ttl_s=86400,
    )
