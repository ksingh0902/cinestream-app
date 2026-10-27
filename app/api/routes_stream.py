# app/api/routes_stream.py
from __future__ import annotations

import json
import re
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


def _find_tmdb_by_imdb(imdb_id: str) -> str | None:
    import httpx
    try:
        r = httpx.get(
            f"https://api.tmdb.org/3/find/{imdb_id}",
            params={"api_key": "15d2ea6d0dc1d476efbca3eba2b9bbfb", "external_source": "imdb_id"},
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            m_res = data.get("movie_results") or []
            if m_res:
                return str(m_res[0]["id"])
            tv_res = data.get("tv_results") or []
            if tv_res:
                return str(tv_res[0]["id"])
    except Exception:
        pass
    return None


def _lookup_dooflix_tmdb_id(title: str, year: str | None, is_series: bool) -> str | None:
    """Resolve a Doo title strictly enough to avoid playing a namesake."""
    import httpx

    clean = re.sub(r"\s*\(\d{4}\).*", "", title or "").strip()
    if not clean:
        return None
    endpoint = "tv" if is_series else "movie"
    params = {
        "api_key": "15d2ea6d0dc1d476efbca3eba2b9bbfb",
        "query": clean,
    }
    # A movie card's year is its release year. A series episode card's year is
    # often the episode year, not the show's first-air year.
    if not is_series and year and str(year).isdigit():
        params["year"] = str(year)
    try:
        response = httpx.get(
            f"https://api.tmdb.org/3/search/{endpoint}", params=params, timeout=6
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        return str(results[0]["id"]) if results else None
    except Exception:
        return None


def _dooflix_embed_url(tmdb_id: str, title: str, is_series: bool, season: int | str | None = None, episode: int | str | None = None) -> str:
    if not is_series:
        return f"https://vidsrc.pm/embed/movie/{tmdb_id}"
    season_no = str(season) if season else None
    episode_no = str(episode) if episode else None
    if not season_no:
        s_m = re.search(r"\bseason\s*(\d+)\b", title or "", re.I)
        season_no = s_m.group(1) if season_no else "1"
    if not episode_no:
        e_m = re.search(r"\bepisode\s*(\d+)\b", title or "", re.I)
        episode_no = e_m.group(1) if episode_no else "1"
    return f"https://vidsrc.pm/embed/tv/{tmdb_id}/{season_no}/{episode_no}"


def _prioritize_dooflix_servers(servers: list[dict]) -> tuple[str, list[dict]]:
    """Prefer verified fast reachable providers."""
    priority = (
        "vip - no ads",
        "vidsrc.si",
        "fast ui - hd",
        "vidfast.pro",
        "vidup.to",
        "vidrock",
        "123embed",
        "videasy",
        "filmu",
        "vidcore",
        "vidsrc",
        "2embed",
    )

    def rank(server: dict) -> int:
        haystack = f"{server.get('label', '')} {server.get('url', '')}".lower()
        return next((index for index, token in enumerate(priority) if token in haystack), len(priority))

    ordered = sorted(servers, key=rank)
    return (ordered[0]["url"] if ordered else ""), ordered


@router.get("/api/stream/{movie_id}")
def stream(
    movie_id: int,
    refresh: bool = False,
    fresh: Optional[int] = 0,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    s: Optional[int] = None,
    e: Optional[int] = None,
):
    target_season = season if season is not None else s
    target_episode = episode if episode is not None else e
    has_ep_params = (target_season is not None) or (target_episode is not None)
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

    if has_ep_params:
        tmdb_id = row["tmdb_id"]
        if not tmdb_id:
            tmdb_id = _lookup_tmdb_id(row["title"], row["year"], is_series=True)
            if tmdb_id:
                with connect() as conn:
                    conn.execute("UPDATE movies SET tmdb_id=? WHERE id=?", (tmdb_id, movie_id))
                    conn.commit()
        if tmdb_id:
            s_num = target_season or 1
            e_num = target_episode or 1
            dummy_url = f"https://embed.vidsrc.si/embed/tv/{tmdb_id}/{s_num}/{e_num}?autoplay=1&ds_lang=en"
            existing_servers = []
            if row["servers_json"]:
                try:
                    existing_servers = json.loads(row["servers_json"])
                except Exception:
                    pass
            main_url, servers = enrich_stream_servers(
                dummy_url,
                is_series=True,
                existing_servers=existing_servers,
                tmdb_id=str(tmdb_id),
                season=s_num,
                episode=e_num,
            )
            if source == "dooflix":
                main_url, servers = _prioritize_dooflix_servers(servers)
            return {
                "kind": "iframe",
                "url": main_url,
                "servers": servers,
                "headers": {},
                "cached": False,
                "type": "iframe",
                "play": main_url,
                "movie_id": movie_id,
                "season": s_num,
                "episode": e_num,
            }

    is_fresh = bool(
        row["player_url"]
        and row["resolved_at"]
        and (time.time() - row["resolved_at"] < CFG.player_ttl_s)
        and "watchkar.com" not in (row["player_url"] or "")
        and "autoembed.cc" not in (row["player_url"] or "")
        and "cluster.dooflix.live" not in (row["player_url"] or "")
    )
    if is_fresh and source == "dooflix" and row["player_kind"] == "iframe":
        sid = str(row["source_id"] or "")
        if not sid.startswith("tt"):
            # For Indian/series titles, re-resolve to get native Speedostream HLS
            is_fresh = False

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
            if source == "dooflix":
                p_url, servers = _prioritize_dooflix_servers(servers)

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
    doo_is_series = bool(row["is_series"]) or bool(
        re.search(r"\b(?:season|episode|s\d{1,2}e\d{1,3})\b", row["title"] or "", re.I)
    )

    # Special handling for DooFlix: resolve Indian titles via Yomovies HLS, and Hollywood via multi-server iframe
    if source == "dooflix":
        sid = str(row["source_id"] or "")
        ym_row = None

        if not sid.startswith("tt"):
            m_id = re.search(r"(\d+)$", sid)
            with connect() as conn:
                conn.row_factory = sqlite3.Row
                if m_id:
                    ym_id = int(m_id.group(1))
                    ym_row = conn.execute("SELECT * FROM movies WHERE id = ? AND source = 'yomovies'", (ym_id,)).fetchone()
                if not ym_row:
                    ym_row = conn.execute("SELECT * FROM movies WHERE title = ? AND source = 'yomovies'", (row["title"],)).fetchone()
                if not ym_row:
                    clean_t = re.sub(r"\s*\(\d{4}\).*", "", row["title"] or "").strip()
                    if clean_t and len(clean_t) > 3:
                        ym_row = conn.execute("SELECT * FROM movies WHERE source = 'yomovies' AND title LIKE ? LIMIT 1", (f"{clean_t}%",)).fetchone()

        if ym_row:
            ym_adapter = registry.get("yomovies")
            ym_detail = ym_row["detail_url"] or ym_row["url"]
            try:
                info = ym_adapter.resolve_stream(ym_detail)
                if info and info.url:
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
            except Exception:
                pass

        # If no Yomovies match or resolution failed: resolve Hollywood / Western titles via TMDB
        if not tmdb_id and sid.startswith("tt"):
            tmdb_id = _find_tmdb_by_imdb(sid)
            if tmdb_id:
                with connect() as conn:
                    conn.execute("UPDATE movies SET tmdb_id=? WHERE id=?", (tmdb_id, movie_id))
                    conn.commit()

        if not tmdb_id:
            tmdb_id = _lookup_dooflix_tmdb_id(row["title"], row["year"], doo_is_series)
            if tmdb_id:
                with connect() as conn:
                    conn.execute("UPDATE movies SET tmdb_id=?, is_series=? WHERE id=?", (tmdb_id, int(doo_is_series), movie_id))
                    conn.commit()

        if tmdb_id:
            dummy_url = _dooflix_embed_url(str(tmdb_id), row["title"], doo_is_series)
            main_url, servers = enrich_stream_servers(dummy_url, is_series=doo_is_series, tmdb_id=str(tmdb_id))
            main_url, servers = _prioritize_dooflix_servers(servers)
            now = int(time.time())
            with connect() as conn:
                conn.execute(
                    "UPDATE movies SET player_url=?, player_kind='iframe', servers_json=?, resolved_at=? WHERE id=?",
                    (main_url, json.dumps(servers), now, movie_id),
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

    if not tmdb_id and detail_url:
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
        info = None
        if tmdb_id and (source == "ask4movie" or row["player_kind"] == "iframe"):
            is_series = doo_is_series if source == "dooflix" else bool(row["is_series"])
            dummy_url = f"https://embed.vidsrc.si/embed/{'tv' if is_series else 'movie'}/{tmdb_id}" + ("/1/1" if is_series else "") + "?autoplay=1&ds_lang=en"
            main_url, servers = enrich_stream_servers(dummy_url, is_series=is_series, tmdb_id=str(tmdb_id))
            if source == "dooflix":
                main_url, servers = _prioritize_dooflix_servers(servers)
            from ..adapters.base import StreamInfo
            info = StreamInfo(kind="iframe", url=main_url, servers=servers)
        elif source == "ask4movie" and detail_url:
            try:
                up_info = adapter.resolve_stream(detail_url)
                if up_info and up_info.url:
                    is_series = bool(row["is_series"])
                    main_url, servers = enrich_stream_servers(
                        up_info.url,
                        is_series=is_series,
                        existing_servers=up_info.servers,
                        tmdb_id=str(tmdb_id) if tmdb_id else None,
                    )
                    from ..adapters.base import StreamInfo
                    info = StreamInfo(kind="iframe", url=main_url, servers=servers)
            except Exception:
                info = None

        if not info:
            info = adapter.resolve_stream(detail_url)
    except Exception as exc:                                      # noqa: BLE001
        if tmdb_id:
            is_series = doo_is_series if source == "dooflix" else bool(row["is_series"])
            dummy_url = (
                _dooflix_embed_url(str(tmdb_id), row["title"], is_series)
                if source == "dooflix"
                else f"https://embed.filmu.in/{'tv' if is_series else 'movie'}/{tmdb_id}" + ("/1/1" if is_series else "")
            )
            main_url, servers = enrich_stream_servers(dummy_url, is_series=is_series, tmdb_id=str(tmdb_id))
            if source == "dooflix":
                main_url, servers = _prioritize_dooflix_servers(servers)
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
                p_url, servers = enrich_stream_servers(
                    p_url,
                    is_series=doo_is_series if source == "dooflix" else bool(row["is_series"]),
                    existing_servers=servers,
                    tmdb_id=str(tmdb_id or "") if source == "dooflix" else None,
                )
                if source == "dooflix":
                    p_url, servers = _prioritize_dooflix_servers(servers)
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
        info.url, info.servers = enrich_stream_servers(
            info.url,
            is_series=doo_is_series if source == "dooflix" else bool(row["is_series"]),
            existing_servers=info.servers,
            tmdb_id=str(tmdb_id or row["tmdb_id"] or "") if (source in ("dooflix", "movies7") or row["tmdb_id"]) else None,
        )
        if source == "dooflix":
            info.url, info.servers = _prioritize_dooflix_servers(info.servers)

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

