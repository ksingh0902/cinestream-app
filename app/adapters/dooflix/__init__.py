"""Database-backed adapter for catalogues imported by dooflix_scraper.py."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import Iterator
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests

from config import DB_PATH, STREAM_TTL

from ..base import MediaItem, SourceAdapter, StreamInfo


class DooflixAdapter(SourceAdapter):
    key = "dooflix"
    label = "doo"
    player_kind = "iframe"
    homepage = ""

    def health(self) -> dict:
        try:
            with closing(sqlite3.connect(DB_PATH, timeout=5)) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM movies WHERE source=?", (self.key,)
                ).fetchone()[0]
            return {"ok": True, "detail": "local import ready", "items": count}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": str(exc)[:200], "items": 0}

    def iter_catalog(self, *, max_pages: int = 0) -> Iterator[MediaItem]:
        del max_pages  # Imported JSON has already been paginated by the CLI.
        with closing(sqlite3.connect(DB_PATH, timeout=5)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM movies WHERE source=? ORDER BY updated_at DESC, id ASC",
                (self.key,),
            ).fetchall()
        for row in rows:
            genres = row["genres"] or ""
            try:
                parsed = json.loads(genres)
                if isinstance(parsed, list):
                    genres = ",".join(str(value) for value in parsed)
            except (TypeError, ValueError):
                pass
            yield MediaItem(
                source=self.key,
                source_id=str(row["source_id"]),
                title=row["title"] or "",
                year=row["year"],
                poster_url=row["poster_url"] or row["poster"],
                duration_s=row["duration_s"],
                rating=row["rating"],
                genres=genres,
                synopsis=row["synopsis"] or "",
                is_series=bool(row["is_series"]),
                detail_url=row["detail_url"] or row["url"],
                player_kind=row["player_kind"] or self.player_kind,
            )

    def enrich(self, item: MediaItem) -> MediaItem:
        return item

    def resolve_stream(self, detail_url: str) -> StreamInfo:
        if not detail_url:
            raise RuntimeError("DooFlix item has no stream or embed URL")

        # The database may contain an already proxied HLS URL from an older
        # import. Unwrap it before applying our proxy exactly once.
        parsed = urlparse(detail_url)
        if parsed.path == "/proxy/hls":
            nested = parse_qs(parsed.query).get("u", [""])[0]
            if nested:
                detail_url = unquote(nested)

        lower = detail_url.lower().split("#", 1)[0]
        if ".m3u8" in lower:
            proxied = f"/proxy/hls?u={quote(detail_url, safe='')}"
            return StreamInfo(
                kind="hls",
                url=proxied,
                servers=[{"label": "DooFlix HLS", "url": proxied}],
                ttl_s=STREAM_TTL,
            )

        # The current APK resolves movies through this host using a TMDB ID.
        # Its response can contain trailing PHP warnings, so decode the first
        # JSON value rather than requiring the entire body to be valid JSON.
        if parsed.netloc == "cluster.dooflix.live":
            try:
                response = requests.get(detail_url, timeout=2)
                response.raise_for_status()
                payload, _ = json.JSONDecoder().raw_decode(response.text)
                streams = payload.get("streams") if isinstance(payload, dict) else []
                streams = streams if isinstance(streams, list) else []

                for stream in streams:
                    if not isinstance(stream, dict) or not stream.get("url"):
                        continue
                    url = str(stream["url"])
                    decoded = unquote(url).lower()
                    if ".m3u8" in decoded:
                        proxied = f"/proxy/hls?u={quote(url, safe='')}"
                        return StreamInfo(
                            kind="hls",
                            url=proxied,
                            servers=[{"label": stream.get("name") or "DooFlix HLS", "url": proxied}],
                            ttl_s=900,
                        )
                    if any(ext in decoded for ext in (".mp4", ".webm")):
                        return StreamInfo(
                            kind="video",
                            url=url,
                            servers=[{"label": stream.get("name") or "DooFlix", "url": url}],
                            headers=stream.get("headers") or {},
                            ttl_s=900,
                        )
            except Exception:
                pass
            raise RuntimeError("DooFlix cluster unavailable")

        raise RuntimeError("DooFlix item has no verified playback target")


adapter = DooflixAdapter()
