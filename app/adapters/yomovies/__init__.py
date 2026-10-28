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

        # 4. Try non-speedostream iframe embeds (e.g. netu.ac, etc.)
        for e in embeds:
            host = (e.get("host") or "").lower()
            url = (e.get("url") or "").lower()
            if "speedo" in host or "speedostream" in url or "/embed-" in url:
                # NEVER return raw speedostream iframe: speedostream blocks iframe embedding with "Embeds disabled3"
                continue
            if e.get("url"):
                return StreamInfo(
                    kind="iframe",
                    url=e["url"],
                    servers=[{"label": e.get("host", "Server 1"), "url": e["url"]}],
                    ttl_s=STREAM_TTL,
                )

        # 5. TMDB & Cinemeta fallback for movies that have upstream matches
        try:
            import re
            import httpx
            with sqlite3.connect(DB_PATH, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                r = conn.execute("SELECT id, title, year, genres, tmdb_id, is_series FROM movies WHERE detail_url=? OR url=?", (detail_url, detail_url)).fetchone()
            if r:
                tid = r["tmdb_id"]
                if not tid:
                    clean_t = re.sub(r"\s*\(\d{4}\).*", "", r["title"] or "").strip()
                    clean_t = re.sub(r"\.\.+$", "", clean_t).strip()
                    if clean_t:
                        try:
                            tmdb_r = httpx.get(
                                "https://api.tmdb.org/3/search/movie",
                                params={"api_key": "15d2ea6d0dc1d476efbca3eba2b9bbfb", "query": clean_t},
                                timeout=4,
                            )
                            if tmdb_r.status_code == 200:
                                res_list = tmdb_r.json().get("results", [])
                                if res_list:
                                    tid = str(res_list[0]["id"])
                        except Exception:
                            pass
                if tid:
                    from ..embed_helper import enrich_stream_servers
                    is_series = bool(r["is_series"])
                    dummy_url = f"https://vidlink.pro/{'tv' if is_series else 'movie'}/{tid}"
                    main_url, servers = enrich_stream_servers(dummy_url, is_series=is_series, tmdb_id=str(tid))
                    return StreamInfo(
                        kind="iframe",
                        url=main_url,
                        servers=servers,
                        ttl_s=STREAM_TTL,
                    )
        except Exception:
            pass

        raise RuntimeError(f"could not resolve stream for {detail_url}")


adapter = YomoviesAdapter()
