"""embed URL -> live signed .m3u8, with TTL cache and fallback host template."""
from __future__ import annotations

import time
from typing import Dict, Optional

from config import DEFAULT_EMBED_HOST, STREAM_TTL
from .http import HttpClient


class StreamResolver:
    def __init__(self, http: HttpClient):
        self.http = http
        self._memo: Dict[str, tuple[float, Optional[Dict]]] = {}

    def cached(self, code: str) -> Optional[Dict]:
        hit = self._memo.get(code)
        if hit and time.time() - hit[0] < STREAM_TTL:
            return hit[1]
        return None

    def resolve(self, code: str, embed_url: Optional[str] = None,
                force: bool = False) -> Optional[Dict]:
        if not force and (c := self.cached(code)):
            return c

        from .extract import parse_embed
        candidates = [embed_url] if embed_url else []
        # R3 fallback: if we only have a code, try the configured host template
        candidates.append(f"{DEFAULT_EMBED_HOST}/embed-{code}.html")

        for url in candidates:
            if not url:
                continue
            try:
                html = self.http.get(url, referer="https://yomovies.wine/", force=True)
                data = parse_embed(html)
            except Exception:
                data = None
            if data:
                data["embed_url"] = url
                self._memo[code] = (time.time(), data)
                return data
        self._memo[code] = (time.time(), None)
        return None
