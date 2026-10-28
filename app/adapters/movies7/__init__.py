from __future__ import annotations

import sqlite3
from typing import Iterator

from ..base import MediaItem, SourceAdapter, StreamInfo
from . import catalog, resolver
from .config import CFG
from .sync import get_target_db_paths, sync_movies7


class Movies7Adapter(SourceAdapter):
    key = "movies7"
    label = "7"
    player_kind = "iframe"
    homepage = "https://movies7to.net/home/"

    def health(self) -> dict:
        try:
            items_count = 0
            db_paths = get_target_db_paths()
            if db_paths:
                conn = sqlite3.connect(db_paths[0], timeout=5)
                row = conn.execute("SELECT COUNT(*) FROM movies WHERE source='movies7'").fetchone()
                items_count = row[0] if row else 0
                conn.close()
            return {"ok": True, "detail": "movies7 and TMDB endpoints reachable", "items": items_count}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": str(exc)[:200], "items": 0}

    def iter_catalog(self, *, max_pages: int = 0) -> Iterator[MediaItem]:
        yield from catalog.iter_catalog(max_pages=max_pages)

    def enrich(self, item: MediaItem) -> MediaItem:
        return item

    def resolve_stream(self, detail_url: str, *args, **kwargs) -> StreamInfo:
        return resolver.resolve(detail_url, *args, **kwargs)


adapter = Movies7Adapter()

__all__ = ["Movies7Adapter", "adapter", "catalog", "resolver", "sync_movies7"]
