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
        primary_url = f"https://cinesrc.st/embed/tv/{tid}/{s}/{e}"
        servers = [
            {"label": "Cinesrc (HD)", "url": f"https://cinesrc.st/embed/tv/{tid}/{s}/{e}"},
            {"label": "111Movies (Multi)", "url": f"https://111movies.net/tv/{tid}/{s}/{e}"},
            {"label": "VidLink (Fast HD)", "url": f"https://vidlink.pro/tv/{tid}/{s}/{e}"},
            {"label": "2Embed (Multi)", "url": f"https://www.2embed.cc/embedtv/{tid}&s={s}&e={e}"},
            {"label": "PrimeSrc (Stream)", "url": f"https://primesrc.me/embed/tv?tmdb={tid}&season={s}&episode={e}"},
        ]
    else:
        primary_url = f"https://cinesrc.st/embed/movie/{tid}"
        servers = [
            {"label": "Cinesrc (HD)", "url": f"https://cinesrc.st/embed/movie/{tid}"},
            {"label": "111Movies (Multi)", "url": f"https://111movies.net/movie/{tid}"},
            {"label": "VidLink (Fast HD)", "url": f"https://vidlink.pro/movie/{tid}"},
            {"label": "2Embed (Multi)", "url": f"https://www.2embed.cc/embed/{tid}"},
            {"label": "PrimeSrc (Stream)", "url": f"https://primesrc.me/embed/movie?tmdb={tid}"},
        ]

    return StreamInfo(
        kind="iframe",
        url=primary_url,
        servers=servers,
        headers={"Referer": "https://movies7to.net/"},
        ttl_s=86400,
    )
