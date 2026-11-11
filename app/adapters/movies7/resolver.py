from __future__ import annotations

import re
from typing import Optional

from ..base import StreamInfo
from ..embed_helper import enrich_stream_servers
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
    Dynamically discovers and verifies available playback sources."""
    tid = str(tmdb_id) if tmdb_id else None
    series_detected = is_series

    if not tid and detail_url:
        m = re.search(r"/(?:tv|movie|watch)/(\d+)", detail_url)
        if m:
            tid = m.group(1)
        if "/tv/" in detail_url:
            series_detected = True

    if not tid:
        m_any = re.search(r"(\d{3,9})", detail_url or "")
        if m_any:
            tid = m_any.group(1)

    s = str(season or 1)
    e = str(episode or 1)

    primary_url, servers = enrich_stream_servers(
        primary_url=detail_url,
        is_series=series_detected,
        tmdb_id=tid,
        season=s,
        episode=e,
        source="movies7",
    )

    return StreamInfo(
        kind="iframe",
        url=primary_url,
        servers=servers,
        headers={"Referer": "https://movies7to.net/"},
        ttl_s=86400,
    )
