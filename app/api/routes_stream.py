# app/api/routes_stream.py
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..adapters import registry
from ..adapters.ask4movie.config import CFG
from ..adapters.ask4movie.sync import connect as writable_connect
from ..adapters.embed_helper import enrich_stream_servers
from ..adapters.movies7 import resolver as movies7_resolver
from .routes_catalog import get_db_connection

router = APIRouter()


_EPISODE_STREAM_CACHE: dict[str, tuple[float, dict]] = {}
_MOVIE_STREAM_CACHE: dict[str, tuple[float, dict]] = {}


def _persist_catalog_update(sql: str, params: tuple) -> None:
    """Best-effort development cache only; production catalogue is immutable."""
    if os.getenv("CATALOG_READ_ONLY", "0") == "1":
        return
    try:
        with writable_connect() as conn:
            conn.execute(sql, params)
            conn.commit()
    except sqlite3.OperationalError:
        # A failed convenience cache write must never prevent playback.
        return


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
        return f"https://embed.filmu.in/movie/{tmdb_id}"
    season_no = str(season) if season else None
    episode_no = str(episode) if episode else None
    if not season_no:
        s_m = re.search(r"\bseason\s*(\d+)\b", title or "", re.I)
        season_no = s_m.group(1) if season_no else "1"
    if not episode_no:
        e_m = re.search(r"\bepisode\s*(\d+)\b", title or "", re.I)
        episode_no = e_m.group(1) if episode_no else "1"
    return f"https://embed.filmu.in/tv/{tmdb_id}/{season_no}/{episode_no}"


def _prioritize_stream_servers(servers: list[dict], source: str = "") -> tuple[str, list[dict]]:
    """Prioritize servers based on source provider and verified reliability:
    1. FilmU - Fast HD is ALWAYS Server 1 (Default / Recommended) for Movies7, DuoFlix, Ask4Movies,
       and YoMovies iframe fallback.
    2. VIP - No ADS is ALWAYS Server 2 (Second default) across all tags.
    3. For native YoMovies Speedostream HLS: Speedostream HLS is Server 1 (Recommended),
       FilmU is Server 2, and VIP - No ADS is Server 3.
    4. Provider-native fast fallbacks (Fast UI, Cinesrc, 111Movies, Ask4 dynamic mirrors) follow.
    """
    if not servers:
        return "", []

    def rank(server: dict) -> int:
        lbl = (server.get("label") or "").lower()
        u = (server.get("url") or "").lower()
        k = (server.get("kind") or "").lower()
        haystack = f"{lbl} {u} {k}"

        has_native_hls = any(
            ("speedo" in (s.get("label", "") + s.get("url", "")).lower() or "/proxy/hls" in (s.get("url", "") or "").lower())
            for s in servers
        )

        # For YoMovies with native HLS: Speedostream is #0, FilmU is #1, VIP is #2
        if source == "yomovies" and has_native_hls:
            if "speedo" in haystack or "/proxy/hls" in u:
                return 0
            if "filmu" in haystack:
                return 1
            if "vip" in haystack or "vidsrc.si" in haystack:
                return 2
            return 3

        # For all other tags (and YoMovies without HLS): FilmU is #0, VIP is #1
        if "filmu" in haystack:
            return 0
        if "vip" in haystack or "vidsrc.si" in haystack:
            return 1
        if "fast ui" in haystack or "vidfast" in haystack:
            return 2
        if "cinesrc" in haystack:
            return 3
        if "111movies" in haystack:
            return 4
        if "123embed" in haystack:
            return 5
        if "vidup" in haystack:
            return 6
        if "vidrock" in haystack:
            return 7
        return 10

    ordered = sorted(servers, key=rank)
    relabeled = []
    seen_urls = set()
    disallowed_hosts = (
        "vidlink.pro",
        "videasy.to",
        "vidcore.org",
        "vidsrc.pm",
        "2embed.cc",
        "primesrc.me",
        "openload.co",
        "oload.download",
        "watchkar.com",
        "autoembed.cc",
        "cluster.dooflix.live",
    )

    for srv in ordered:
        u = srv.get("url") or ""
        if not u or u in seen_urls:
            continue
        u_lower = u.lower()
        if any(dh in u_lower for dh in disallowed_hosts):
            continue
        seen_urls.add(u)

        lbl = srv.get("label") or ""
        lbl_lower = lbl.lower()
        k = srv.get("kind") or ("hls" if ("/proxy/hls" in u_lower or "speedo" in u_lower) else "iframe")

        if "speedo" in u_lower or "speedo" in lbl_lower or "/proxy/hls" in u_lower:
            srv_name = "Speedostream HLS"
            k = "hls"
        elif "filmu" in u_lower:
            srv_name = "FilmU - Fast HD"
            k = "iframe"
        elif "vidsrc.si" in u_lower or "vip" in lbl_lower:
            srv_name = "VIP - No ADS"
            k = "iframe"
        elif "vidfast" in u_lower or "fast ui" in lbl_lower:
            srv_name = "Fast UI - HD"
            k = "iframe"
        elif "cinesrc" in u_lower or "cinesrc" in lbl_lower:
            srv_name = "Cinesrc - HD"
            k = "iframe"
        elif "111movies" in u_lower:
            srv_name = "111Movies - Multi"
            k = "iframe"
        elif "123embed" in u_lower:
            srv_name = "123Embed - Multi"
            k = "iframe"
        elif "vidup" in u_lower:
            srv_name = "VidUp"
            k = "iframe"
        elif "vidrock" in u_lower:
            srv_name = "VidRock"
            k = "iframe"
        elif "(" in lbl:
            clean_lbl = re.sub(r"\s*\(Recommended\)", "", lbl, flags=re.I).strip()
            srv_name = clean_lbl.split("(", 1)[-1].rstrip(")").strip()
            if ")" in srv_name:
                srv_name = srv_name.split(")")[0].strip()
        else:
            srv_name = re.sub(r"\s*\(Recommended\)", "", lbl, flags=re.I).strip() or "HD"

        idx = len(relabeled) + 1
        rec_tag = " (Recommended)" if idx == 1 else ""
        relabeled.append({
            "label": f"Server {idx} ({srv_name}){rec_tag}",
            "url": u,
            "kind": k,
        })

    main_url = relabeled[0]["url"] if relabeled else ""
    return main_url, relabeled


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

    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM movies WHERE id = ?", (movie_id,)).fetchone()

    if not row:
        raise HTTPException(404, "not found")

    source = row["source"] or "yomovies"
    adapter = registry.get(source)
    if adapter is None:
        raise HTTPException(500, f"no adapter for source {source}")

    is_series_record = bool(row["is_series"]) or bool(re.search(r"\b(?:season\s*\d+|s\d+\s*e\d+)\b", row["title"] or "", re.I))
    if has_ep_params and not is_series_record:
        # Ignore client-passed season/episode parameters for movies so they are never resolved as TV series
        has_ep_params = False
        target_season = None
        target_episode = None

    if has_ep_params:
        s_num = target_season or 1
        e_num = target_episode or 1
        ep_cache_key = f"{movie_id}:s{s_num}:e{e_num}"

        if not force_refresh and ep_cache_key in _EPISODE_STREAM_CACHE:
            exp, cached_res = _EPISODE_STREAM_CACHE[ep_cache_key]
            if time.time() < exp:
                return {**cached_res, "cached": True}

        tmdb_id = row["tmdb_id"]
        if not tmdb_id:
            tmdb_id = _lookup_tmdb_id(row["title"], row["year"], is_series=True)
            if tmdb_id:
                _persist_catalog_update("UPDATE movies SET tmdb_id=? WHERE id=?", (tmdb_id, movie_id))

        if source == "movies7":
            try:
                info = movies7_resolver.resolve(
                    row["detail_url"] or row["url"] or "",
                    tmdb_id=tmdb_id,
                    is_series=True,
                    season=s_num,
                    episode=e_num,
                )
                res = {
                    "kind": info.kind,
                    "url": info.url,
                    "servers": info.servers,
                    "headers": info.headers,
                    "cached": False,
                    "type": info.kind,
                    "play": info.url,
                    "movie_id": movie_id,
                    "season": s_num,
                    "episode": e_num,
                }
                _EPISODE_STREAM_CACHE[ep_cache_key] = (time.time() + 3600, res)
                return res
            except Exception:
                pass

        if tmdb_id:
            dummy_url = f"https://embed.filmu.in/tv/{tmdb_id}/{s_num}/{e_num}"
            main_url, servers = enrich_stream_servers(
                dummy_url,
                is_series=True,
                tmdb_id=str(tmdb_id),
                season=s_num,
                episode=e_num,
                source=source,
            )
            res = {
                "kind": "iframe" if servers else "hls",
                "url": main_url,
                "servers": servers,
                "headers": {},
                "cached": False,
                "type": "iframe" if servers else "hls",
                "play": main_url,
                "movie_id": movie_id,
                "season": s_num,
                "episode": e_num,
            }
            _EPISODE_STREAM_CACHE[ep_cache_key] = (time.time() + 3600, res)
            return res

    m_cache_key = str(movie_id)
    if not force_refresh and m_cache_key in _MOVIE_STREAM_CACHE:
        exp, cached_res = _MOVIE_STREAM_CACHE[m_cache_key]
        if time.time() < exp:
            return {**cached_res, "cached": True}

    row_embeds = []
    if row["embeds"]:
        try:
            row_embeds = json.loads(row["embeds"])
        except Exception:
            pass

    is_fresh = bool(
        row["player_url"]
        and row["resolved_at"]
        and (time.time() - row["resolved_at"] < CFG.player_ttl_s)
        and "watchkar.com" not in (row["player_url"] or "")
        and "autoembed.cc" not in (row["player_url"] or "")
        and "cluster.dooflix.live" not in (row["player_url"] or "")
    )
    # Older Movies7 responses were accidentally rewritten to the generic
    # VidSrc server list.  Re-resolve those once so the adapter's native
    # Movies7 player/servers are restored; valid Movies7 Videasy caches remain
    # usable without another upstream request.
    if is_fresh and source == "movies7":
        cached_urls = [(row["player_url"] or "").lower()]
        if row["servers_json"]:
            try:
                cached_urls.extend(
                    str(server.get("url") or "").lower()
                    for server in json.loads(row["servers_json"])
                    if isinstance(server, dict)
                )
            except Exception:
                pass
        # Re-resolve movies7 cache so FilmU is primary
        if "embed.filmu.in" not in (row["player_url"] or "").lower():
            is_fresh = False
    # Invalidate stale /tv/ player_url or servers cached on a movie
    if is_fresh and not is_series_record and ("/tv/" in (row["player_url"] or "") or (row["servers_json"] and "/tv/" in row["servers_json"])):
        is_fresh = False
    # Invalidate stale speedostream iframe embeds which show Embeds disabled3
    if is_fresh and "speedostream" in (row["player_url"] or "").lower() and row["player_kind"] == "iframe":
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
        if p_kind == "iframe" and source != "movies7":
            p_url, servers = enrich_stream_servers(
                p_url,
                is_series=is_series_record,
                existing_servers=servers,
                tmdb_id=str(row["tmdb_id"] or ""),
                embeds=row_embeds,
                source=source,
            )
        p_url, servers = _prioritize_stream_servers(servers or ([{"label": "Server 1", "url": p_url, "kind": p_kind}] if p_url else []), source=source)

        res = {
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
        _MOVIE_STREAM_CACHE[m_cache_key] = (time.time() + (1800 if p_kind == "hls" else 3600), res)
        return res

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
            with get_db_connection() as conn:
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
                    _persist_catalog_update(
                        "UPDATE movies SET player_url=?, player_kind=?, servers_json=?, resolved_at=? WHERE id=?",
                        (info.url, info.kind, json.dumps(info.servers), now, movie_id),
                    )
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
                _persist_catalog_update("UPDATE movies SET tmdb_id=? WHERE id=?", (tmdb_id, movie_id))

        if not tmdb_id:
            tmdb_id = _lookup_dooflix_tmdb_id(row["title"], row["year"], doo_is_series)
            if tmdb_id:
                _persist_catalog_update(
                    "UPDATE movies SET tmdb_id=?, is_series=? WHERE id=?", (tmdb_id, int(doo_is_series), movie_id)
                )

        if tmdb_id:
            dummy_url = _dooflix_embed_url(str(tmdb_id), row["title"], doo_is_series)
            main_url, servers = enrich_stream_servers(dummy_url, is_series=doo_is_series, tmdb_id=str(tmdb_id), embeds=row_embeds, source="dooflix")
            main_url, servers = _prioritize_stream_servers(servers, source="dooflix")
            now = int(time.time())
            _persist_catalog_update(
                "UPDATE movies SET player_url=?, player_kind='iframe', servers_json=?, resolved_at=? WHERE id=?",
                (main_url, json.dumps(servers), now, movie_id),
            )
            res = {
                "kind": "iframe",
                "url": main_url,
                "servers": servers,
                "headers": {},
                "cached": False,
                "type": "iframe",
                "play": main_url,
                "movie_id": movie_id,
            }
            _MOVIE_STREAM_CACHE[m_cache_key] = (time.time() + 3600, res)
            return res

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
            _persist_catalog_update("UPDATE movies SET tmdb_id=? WHERE id=?", (tmdb_id, movie_id))

    if not detail_url and not tmdb_id:
        raise HTTPException(502, "no detail url available for stream resolution")

    try:
        info = None
        if tmdb_id and source != "movies7" and (source == "ask4movie" or row["player_kind"] == "iframe"):
            is_series = doo_is_series if source == "dooflix" else bool(row["is_series"])
            dummy_url = f"https://embed.filmu.in/{'tv' if is_series else 'movie'}/{tmdb_id}" + ("/1/1" if is_series else "")
            main_url, servers = enrich_stream_servers(dummy_url, is_series=is_series, tmdb_id=str(tmdb_id), embeds=row_embeds, source=source)
            main_url, servers = _prioritize_stream_servers(servers, source=source)
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
                        embeds=row_embeds,
                        source=source,
                    )
                    from ..adapters.base import StreamInfo
                    info = StreamInfo(kind="iframe", url=main_url, servers=servers)
            except Exception:
                info = None

        if not info:
            if source == "movies7":
                info = movies7_resolver.resolve(
                    detail_url,
                    tmdb_id=tmdb_id,
                    is_series=bool(row["is_series"]),
                    season=season,
                    episode=episode,
                )
            else:
                info = adapter.resolve_stream(detail_url)
    except Exception as exc:                                      # noqa: BLE001
        if tmdb_id:
            is_series = doo_is_series if source == "dooflix" else bool(row["is_series"])
            dummy_url = (
                _dooflix_embed_url(str(tmdb_id), row["title"], is_series)
                if source == "dooflix"
                else f"https://embed.filmu.in/{'tv' if is_series else 'movie'}/{tmdb_id}" + ("/1/1" if is_series else "")
            )
            main_url, servers = enrich_stream_servers(dummy_url, is_series=is_series, tmdb_id=str(tmdb_id), embeds=row_embeds, source=source)
            main_url, servers = _prioritize_stream_servers(servers, source=source)
            now = int(time.time())
            _persist_catalog_update(
                "UPDATE movies SET player_url=?, player_kind=?, servers_json=?, resolved_at=? WHERE id=?",
                (main_url, "iframe", json.dumps(servers), now, movie_id),
            )
            res = {
                "kind": "iframe",
                "url": main_url,
                "servers": servers,
                "headers": {},
                "cached": False,
                "type": "iframe",
                "play": main_url,
                "movie_id": movie_id,
            }
            _MOVIE_STREAM_CACHE[m_cache_key] = (time.time() + 3600, res)
            return res
        if row["player_url"]:
            servers = []
            if row["servers_json"]:
                try:
                    servers = json.loads(row["servers_json"])
                except Exception:
                    pass
            p_kind = row["player_kind"] or adapter.player_kind
            p_url = row["player_url"]
            if p_kind == "iframe" and source != "movies7":
                p_url, servers = enrich_stream_servers(
                    p_url,
                    is_series=doo_is_series if source == "dooflix" else is_series_record,
                    existing_servers=servers,
                    tmdb_id=str(tmdb_id or row["tmdb_id"] or "") or None,
                    embeds=row_embeds,
                    source=source,
                )
            p_url, servers = _prioritize_stream_servers(servers or ([{"label": "Server 1", "url": p_url, "kind": p_kind}] if p_url else []), source=source)
            res = {
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
            _MOVIE_STREAM_CACHE[m_cache_key] = (time.time() + (1800 if p_kind == "hls" else 3600), res)
            return res
        raise HTTPException(502, str(exc)[:200])

    if info.kind == "iframe" and source != "movies7":
        info.url, info.servers = enrich_stream_servers(
            info.url,
            is_series=doo_is_series if source == "dooflix" else is_series_record,
            existing_servers=info.servers,
            tmdb_id=str(tmdb_id or row["tmdb_id"] or "") or None,
            embeds=row_embeds,
            source=source,
        )
    info.url, info.servers = _prioritize_stream_servers(info.servers or ([{"label": "Server 1", "url": info.url, "kind": info.kind}] if info.url else []), source=source)

    now = int(time.time())
    _persist_catalog_update(
        "UPDATE movies SET player_url=?, player_kind=?, servers_json=?, resolved_at=? WHERE id=?",
        (info.url, info.kind, json.dumps(info.servers), now, movie_id),
    )

    res = {
        "kind": info.kind,
        "url": info.url,
        "servers": info.servers,
        "headers": info.headers,
        "cached": False,
        "type": info.kind,
        "play": info.url,
        "movie_id": movie_id,
    }
    _MOVIE_STREAM_CACHE[m_cache_key] = (time.time() + (1800 if info.kind == "hls" else 3600), res)
    return res

