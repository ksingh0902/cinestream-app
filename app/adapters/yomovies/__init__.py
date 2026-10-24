from __future__ import annotations

import json
import sqlite3
from typing import Iterator
from urllib.parse import quote

from config import CRAWL_DELAY, DB_PATH, DEFAULT_EMBED_HOST, SITE_MIRRORS, STREAM_TTL
from scraper.extract import parse_detail, parse_listing, parse_pagination
from scraper.http import HttpClient
from scraper.resolve import StreamResolver
from ..base import MediaItem, SourceAdapter, StreamInfo


class YomoviesAdapter(SourceAdapter):
    key = "yomovies"
    label = "ym"
    player_kind = "hls"
    homepage = SITE_MIRRORS[0] if SITE_MIRRORS else "https://yomovies.wine"

    def __init__(self):
        self._http = HttpClient(delay=0.0, cache_dir=".cache")
        self._resolver = StreamResolver(self._http)

    def health(self) -> dict:
        try:
            self._http.get(self.homepage + "/", force=True)
            items_count = 0
            try:
                conn = sqlite3.connect(DB_PATH, timeout=5)
                items_count = conn.execute("SELECT COUNT(*) FROM movies WHERE source='yomovies'").fetchone()[0]
                conn.close()
            except Exception:
                pass
            return {"ok": True, "detail": "site reachable", "items": items_count}
        except Exception as exc:                                  # noqa: BLE001
            return {"ok": False, "detail": str(exc)[:200], "items": 0}

    def iter_catalog(self, *, max_pages: int = 0) -> Iterator[MediaItem]:
        page = 1
        limit_pages = max_pages if max_pages > 0 else 50
        while page <= limit_pages:
            url = f"{self.homepage}/genre/bollywood/" if page == 1 else f"{self.homepage}/genre/bollywood/page/{page}/"
            try:
                html = self._http.get(url)
            except Exception:
                break
            cards = parse_listing(html, self.homepage)
            if not cards:
                break
            for c in cards:
                slug = c.get("slug") or c["url"].rstrip("/").split("/")[-1]
                yield MediaItem(
                    source="yomovies",
                    source_id=slug,
                    title=c.get("title", ""),
                    year=int(c["year"]) if c.get("year") and str(c["year"]).isdigit() else None,
                    poster_url=c.get("poster"),
                    rating=None,
                    is_series=bool(c.get("is_series", False)),
                    detail_url=c.get("url"),
                    player_kind="hls",
                )
            if not parse_pagination(html, self.homepage):
                break
            page += 1

    def enrich(self, item: MediaItem) -> MediaItem:
        if not item.detail_url:
            return item
        try:
            html = self._http.get(item.detail_url)
            info = parse_detail(html, item.detail_url)
            item.synopsis = info.get("synopsis") or item.synopsis
            item.genres = ",".join(info.get("genres") or []) if isinstance(info.get("genres"), list) else (info.get("genres") or "")
            item.duration_s = info.get("duration_s") or item.duration_s
            if info.get("imdb"):
                try:
                    cleaned = info["imdb"].replace("IMDb: ", "").replace("★ ", "").strip()
                    item.rating = float(cleaned)
                except Exception:
                    pass
            if info.get("poster"):
                item.poster_url = info["poster"]
        except Exception:
            pass
        return item

    def resolve_stream(self, detail_url: str) -> StreamInfo:
        """Resolve live HLS or fallback embed from permanent detail_url."""
        # 1. Check if we already have embed info in DB
        embeds = []
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT embeds FROM movies WHERE detail_url = ? OR url = ?",
                               (detail_url, detail_url)).fetchone()
            if row and row["embeds"]:
                embeds = json.loads(row["embeds"])
            conn.close()
        except Exception:
            pass

        # 2. If no embeds, scrape detail page
        if not embeds:
            html = self._http.get(detail_url, force=True)
            info = parse_detail(html, detail_url)
            embeds = info.get("embeds") or []
            if embeds:
                try:
                    conn = sqlite3.connect(DB_PATH, timeout=5)
                    conn.execute("UPDATE movies SET embeds=? WHERE detail_url=? OR url=?",
                                 (json.dumps(embeds), detail_url, detail_url))
                    conn.commit()
                    conn.close()
                except Exception:
                    pass

        # 3. Try Speedostream HLS
        for e in embeds:
            host = (e.get("host") or "").lower()
            url = (e.get("url") or "").lower()
            is_speedo = e.get("type") == "speedo" or "speedo" in host or "/embed-" in url
            if is_speedo:
                data = self._resolver.resolve(e["code"], e.get("url"), force=True)
                if data and data.get("hls"):
                    hls_url = f"/proxy/hls?u={quote(data['hls'], safe='')}"
                    return StreamInfo(
                        kind="hls",
                        url=hls_url,
                        servers=[{"label": "Speedostream (HLS)", "url": hls_url}],
                        ttl_s=STREAM_TTL,
                    )

        # 4. Try iframe embeds
        for e in embeds:
            if e.get("url"):
                return StreamInfo(
                    kind="iframe",
                    url=e["url"],
                    servers=[{"label": e.get("host", "Server 1"), "url": e["url"]}],
                    ttl_s=STREAM_TTL,
                )

        # 5. Cinemeta fallback for Hollywood/international titles
        try:
            import re
            import httpx
            with sqlite3.connect(DB_PATH, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                r = conn.execute("SELECT title, year, genres FROM movies WHERE detail_url=? OR url=?", (detail_url, detail_url)).fetchone()
            if r:
                genres = (r["genres"] or "").lower()
                title_lower = (r["title"] or "").lower()
                is_regional = any(k in genres for k in ["punjabi", "bollywood", "marathi", "bengali", "tamil", "telugu"]) or \
                              any(k in title_lower for k in ["punjabi", "hindi", "bengali", "marathi", "tamil", "telugu", "season"])
                if not is_regional:
                    clean_title = re.sub(r'\(\d{4}\).*', '', r["title"] or "").strip()
                    query = f"{clean_title} {r['year'] or ''}".strip()
                    c_url = f"https://v3-cinemeta.strem.io/catalog/movie/top/search={quote(query)}.json"
                    with httpx.Client(timeout=6, follow_redirects=True) as client:
                        cr = client.get(c_url)
                        metas = cr.json().get("metas", [])
                        if metas and metas[0].get("id") and str(metas[0]["id"]).startswith("tt"):
                            meta_name = (metas[0].get("name") or "").lower()
                            clean_name = re.sub(r'[^a-z0-9 ]', '', clean_title.lower()).strip()
                            if clean_name and (clean_name in meta_name or meta_name in clean_name):
                                imdb_id = metas[0]["id"]
                                fallback_url = f"https://vidsrc.sh/embed/movie?imdb={imdb_id}"
                                return StreamInfo(
                                    kind="iframe",
                                    url=fallback_url,
                                    servers=[{"label": "vidsrc.sh", "url": fallback_url}],
                                    ttl_s=STREAM_TTL,
                                )
        except Exception:
            pass

        raise RuntimeError(f"could not resolve stream for {detail_url}")


adapter = YomoviesAdapter()
