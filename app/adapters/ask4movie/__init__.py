from __future__ import annotations

from typing import Iterator

from ..base import MediaItem, SourceAdapter, StreamInfo
from . import catalog, resolver
from .config import CFG


class Ask4MovieAdapter(SourceAdapter):
    key = "ask4movie"
    label = "ask"
    player_kind = "iframe"
    homepage = "https://ask4movietv.cyou"

    def health(self) -> dict:
        try:
            catalog.get(CFG.catalog_mirrors[0] + "/movies/")
            catalog.get(CFG.stream_mirrors[0])
            # Count items in database if accessible
            items_count = 0
            try:
                import sqlite3
                conn = sqlite3.connect(CFG.db_path, timeout=5)
                items_count = conn.execute("SELECT COUNT(*) FROM movies WHERE source='ask4movie'").fetchone()[0]
                conn.close()
            except Exception:
                pass
            return {"ok": True, "detail": "catalog and stream hosts reachable", "items": items_count}
        except Exception as exc:                                  # noqa: BLE001
            return {"ok": False, "detail": str(exc)[:200], "items": 0}

    def iter_catalog(self, *, max_pages: int = 0) -> Iterator[MediaItem]:
        # primary sweep, then two extra seeds for recency coverage
        for seed in ("/movies/", "/latest/", "/top-imdb/"):
            yield from catalog.crawl_listing(seed, max_pages=max_pages)

    def enrich(self, item: MediaItem) -> MediaItem:
        return catalog.enrich(item)

    def resolve_stream(self, detail_url: str) -> StreamInfo:
        return resolver.resolve(detail_url)


adapter = Ask4MovieAdapter()
