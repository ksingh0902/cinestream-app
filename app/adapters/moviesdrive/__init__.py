"""Source adapter for MoviesDrive (https://new5.moviesdrive.cyou / https://moviesdrives.bid)."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import Iterator, Optional

from config import DB_PATH

from ..base import MediaItem, SourceAdapter, StreamInfo
from ..embed_helper import enrich_stream_servers
from . import catalog


class MoviesDriveAdapter(SourceAdapter):
    key = "moviesdrive"
    label = "md"
    player_kind = "iframe"
    homepage = f"{catalog.MOVIESDRIVE_MIRRORS[0]}/"

    def health(self) -> dict:
        try:
            with closing(sqlite3.connect(DB_PATH, timeout=5)) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM movies WHERE source=?", (self.key,)
                ).fetchone()[0]
            return {"ok": True, "detail": "moviesdrive adapter ready", "items": count}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": str(exc)[:200], "items": 0}

    def iter_catalog(self, *, max_pages: int = 3) -> Iterator[MediaItem]:
        yield from catalog.iter_catalog(max_pages=max_pages)

    def enrich(self, item: MediaItem) -> MediaItem:
        return item

    def resolve_stream(
        self,
        detail_url: str,
        *,
        tmdb_id: Optional[int | str] = None,
        imdb_id: Optional[str] = None,
        is_series: bool = False,
        season: Optional[int | str] = None,
        episode: Optional[int | str] = None,
    ) -> StreamInfo:
        tid = str(tmdb_id) if tmdb_id else None
        iid = imdb_id
        series_detected = bool(is_series)

        if (not tid and not iid) and detail_url:
            try:
                with closing(sqlite3.connect(DB_PATH, timeout=5)) as conn:
                    row = conn.execute(
                        "SELECT tmdb_id, imdb, is_series FROM movies WHERE source='moviesdrive' AND (detail_url=? OR url=?) LIMIT 1",
                        (detail_url, detail_url),
                    ).fetchone()
                    if row:
                        if row[0]:
                            tid = str(row[0])
                        if row[1]:
                            iid = str(row[1])
                        if row[2]:
                            series_detected = True
            except Exception:
                pass

        primary_url, servers = enrich_stream_servers(
            primary_url=detail_url,
            is_series=series_detected,
            tmdb_id=tid,
            season=str(season or 1),
            episode=str(episode or 1),
            source=self.key,
        )
        return StreamInfo(
            kind="iframe",
            url=primary_url,
            servers=servers,
            headers={"Referer": f"{catalog.MOVIESDRIVE_MIRRORS[0]}/"},
            ttl_s=86400,
        )


adapter = MoviesDriveAdapter()
