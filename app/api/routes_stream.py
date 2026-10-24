# app/api/routes_stream.py
from __future__ import annotations

import json
import sqlite3
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..adapters import registry
from ..adapters.ask4movie.config import CFG
from ..adapters.ask4movie.sync import connect
from ..adapters.embed_helper import enrich_stream_servers

router = APIRouter()


def _lookup_tmdb_id(title: str, year: str | None = None, is_series: bool = False) -> str | None:
    import httpx
    import re
    clean = re.sub(r"\s*\(\d{4}\).*", "", title or "").strip()
    clean = re.sub(r"\.\.+$", "", clean).strip()
    if not clean:
        return None
    endpoint = "tv" if is_series else "movie"
    params = {"api_key": "15d2ea6d0dc1d476efbca3eba2b9bbfb", "query": clean}
    if year and str(year).isdigit() and int(year) <= 2025:
        params["year" if not is_series else "first_air_date_year"] = str(year)
    try:
        r = httpx.get(f"https://api.tmdb.org/3/search/{endpoint}", params=params, timeout=4)
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                return str(results[0]["id"])
    except Exception:
        pass
    return None


@router.get("/api/stream/{movie_id}")
def stream(
    movie_id: int,
    refresh: bool = False,
    fresh: Optional[int] = 0,
):
    force_refresh = bool(refresh or fresh)

    with connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM movies WHERE id = ?", (movie_id,)).fetchone()

    if not row:
        raise HTTPException(404, "not found")

    source = row["source"] or "yomovies"
    adapter = registry.get(source)
    if adapter is None:
        raise HTTPException(500, f"no adapter for source {source}")

    is_fresh = bool(
        row["player_url"]
        and row["resolved_at"]
        and (time.time() - row["resolved_at"] < CFG.player_ttl_s)
    )

    if is_fresh and not force_refresh:
        servers = []
        if row["servers_json"]:
            try:
                servers = json.loads(row["servers_json"])
            except Exception:
                pass

        p_kind = row["player_kind"] or adapter.player_kind
        p_url = row["player_url"]
        if p_kind == "iframe":
            p_url, servers = enrich_stream_servers(p_url, is_series=bool(row["is_series"]), existing_servers=servers, tmdb_id=str(row["tmdb_id"] or ""))

        return {
            "kind": p_kind,
            "url": p_url,
            "servers": servers,
            "headers": {},
            "cached": True,
            # Compatibility fields for legacy frontend
            "type": p_kind,
            "play": p_url,
            "movie_id": movie_id,
        }

    detail_url = row["detail_url"] or row["url"]
    tmdb_id = row["tmdb_id"]
    if not tmdb_id and detail_url:
        import re
        m_tid = re.search(r"-(\d+)/?$", detail_url)
        if m_tid:
            cand = m_tid.group(1)
            # If it's a 4-digit year (19xx or 20xx), it's a release year slug, not a TMDB ID
            if not (len(cand) == 4 and (cand.startswith("19") or cand.startswith("20"))):
                tmdb_id = cand

    if not tmdb_id and (source == "ask4movie" or row["player_kind"] == "iframe"):
        tmdb_id = _lookup_tmdb_id(row["title"], row["year"], bool(row["is_series"]))
        if tmdb_id:
            with connect() as conn:
                conn.execute("UPDATE movies SET tmdb_id=? WHERE id=?", (tmdb_id, movie_id))
                conn.commit()

    if not detail_url and not tmdb_id:
        raise HTTPException(502, "no detail url available for stream resolution")

    try:
        if tmdb_id and (source == "ask4movie" or row["player_kind"] == "iframe"):
            is_series = bool(row["is_series"])
            dummy_url = f"https://vidsrc.pm/embed/{'tv' if is_series else 'movie'}/{tmdb_id}" + ("/1/1" if is_series else "")
            main_url, servers = enrich_stream_servers(dummy_url, is_series=is_series, tmdb_id=str(tmdb_id))
            from ..adapters.base import StreamInfo
            info = StreamInfo(kind="iframe", url=main_url, servers=servers)
        else:
            info = adapter.resolve_stream(detail_url)
    except Exception as exc:                                      # noqa: BLE001
        if tmdb_id:
            is_series = bool(row["is_series"])
            dummy_url = f"https://vidsrc.pm/embed/{'tv' if is_series else 'movie'}/{tmdb_id}" + ("/1/1" if is_series else "")
            main_url, servers = enrich_stream_servers(dummy_url, is_series=is_series, tmdb_id=str(tmdb_id))
            now = int(time.time())
            with connect() as conn:
                conn.execute(
                    "UPDATE movies SET player_url=?, player_kind=?, servers_json=?, resolved_at=? WHERE id=?",
                    (main_url, "iframe", json.dumps(servers), now, movie_id),
                )
                conn.commit()
            return {
                "kind": "iframe",
                "url": main_url,
                "servers": servers,
                "headers": {},
                "cached": False,
                "type": "iframe",
                "play": main_url,
                "movie_id": movie_id,
            }
        if row["player_url"]:
            servers = []
            if row["servers_json"]:
                try:
                    servers = json.loads(row["servers_json"])
                except Exception:
                    pass
            p_kind = row["player_kind"] or adapter.player_kind
            p_url = row["player_url"]
            if p_kind == "iframe":
                p_url, servers = enrich_stream_servers(p_url, is_series=bool(row["is_series"]), existing_servers=servers)
            return {
                "kind": p_kind,
                "url": p_url,
                "servers": servers,
                "headers": {},
                "cached": True,
                "warning": str(exc)[:200],
                "type": p_kind,
                "play": p_url,
                "movie_id": movie_id,
            }
        raise HTTPException(502, str(exc)[:200])

    if info.kind == "iframe":
        info.url, info.servers = enrich_stream_servers(info.url, is_series=bool(row["is_series"]), existing_servers=info.servers)

    now = int(time.time())
    with connect() as conn:
        conn.execute(
            "UPDATE movies SET player_url=?, player_kind=?, servers_json=?, resolved_at=? WHERE id=?",
            (info.url, info.kind, json.dumps(info.servers), now, movie_id),
        )
        conn.commit()

    return {
        "kind": info.kind,
        "url": info.url,
        "servers": info.servers,
        "headers": info.headers,
        "cached": False,
        "type": info.kind,
        "play": info.url,
        "movie_id": movie_id,
    }

