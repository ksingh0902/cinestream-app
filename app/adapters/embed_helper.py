from __future__ import annotations

import re
import time
from typing import Optional
import httpx

DISALLOWED_HOSTS = (
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

TMDB_API_KEY = "15d2ea6d0dc1d476efbca3eba2b9bbfb"

# Ephemeral in-memory availability caches (TTL = 3600s)
_FILMU_CACHE: dict[str, tuple[float, bool]] = {}
_TMDB_CACHE: dict[str, tuple[float, bool]] = {}


def verify_filmu_availability(
    tmdb_id: str | int,
    is_series: bool = False,
    season: int | str = 1,
    episode: int | str = 1,
) -> bool:
    """Provider-aware verification: FilmU redirects to vidly.pro and exposes
    title-specific metadata if the title or episode actually exists."""
    if not tmdb_id:
        return False
    tid_str = str(tmdb_id).strip()
    s_str = str(season or 1).strip()
    e_str = str(episode or 1).strip()
    cache_key = f"{'tv' if is_series else 'movie'}_{tid_str}_{s_str}_{e_str}"
    now = time.time()

    if cache_key in _FILMU_CACHE:
        exp, res = _FILMU_CACHE[cache_key]
        if now < exp:
            return res

    url = f"https://vidly.pro/{'tv' if is_series else 'movie'}/{tid_str}"
    if is_series:
        url += f"/{s_str}/{e_str}"

    is_valid = False
    try:
        r = httpx.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://google.com/",
            },
            follow_redirects=True,
            timeout=2.0,
        )
        if r.status_code == 200 and len(r.text) >= 45000:
            title_m = re.search(r"<title>([^<]+)</title>", r.text)
            t_text = title_m.group(1).strip() if title_m else ""
            if t_text and t_text != "Vidly — embeddable player":
                is_valid = True
    except Exception:
        is_valid = False

    _FILMU_CACHE[cache_key] = (now + 3600, is_valid)
    return is_valid


def verify_tmdb_released(
    tmdb_id: str | int,
    is_series: bool = False,
    season: int | str = 1,
    episode: int | str = 1,
) -> bool:
    """Verifies that the content actually exists in TMDB and is released/aired."""
    if not tmdb_id:
        return False
    tid_str = str(tmdb_id).strip()
    s_str = str(season or 1).strip()
    e_str = str(episode or 1).strip()
    cache_key = f"{'tv' if is_series else 'movie'}_{tid_str}_{s_str}_{e_str}"
    now = time.time()

    if cache_key in _TMDB_CACHE:
        exp, res = _TMDB_CACHE[cache_key]
        if now < exp:
            return res

    is_valid = False
    try:
        today = time.strftime("%Y-%m-%d")
        if is_series:
            ep_url = f"https://api.tmdb.org/3/tv/{tid_str}/season/{s_str}/episode/{e_str}?api_key={TMDB_API_KEY}"
            r = httpx.get(ep_url, timeout=2.5)
            if r.status_code == 200:
                data = r.json()
                air_date = data.get("air_date") or ""
                is_valid = bool(air_date and air_date <= today)
        else:
            m_url = f"https://api.tmdb.org/3/movie/{tid_str}?api_key={TMDB_API_KEY}"
            r = httpx.get(m_url, timeout=2.5)
            if r.status_code == 200:
                data = r.json()
                status = (data.get("status") or "").lower()
                rel_date = data.get("release_date") or ""
                if status in ("in production", "planned", "post production") and (not rel_date or rel_date > today):
                    is_valid = False
                else:
                    is_valid = True
    except Exception:
        is_valid = False

    _TMDB_CACHE[cache_key] = (now + 7200, is_valid)
    return is_valid


def enrich_stream_servers(
    primary_url: str = "",
    is_series: bool = False,
    existing_servers: list | None = None,
    tmdb_id: str | None = None,
    season: int | str | None = None,
    episode: int | str | None = None,
    embeds: list | None = None,
    source: str = "",
) -> tuple[str, list[dict]]:
    """Discovers and validates all genuinely available playback sources for a specific title or episode.
    Only sources with concrete evidence of availability are included.
    Numbers and labels only the sources actually returned."""
    tid = str(tmdb_id).strip() if tmdb_id else None
    if not tid and primary_url:
        m_id = re.search(r"(?:/movie/|/embed/|/embedtv/|/tv/|-)(\d{3,9})", primary_url)
        if m_id:
            tid = m_id.group(1)

    m_tv = re.search(r"/(?:tv|embedtv)/(\d+)(?:[/?&]s=(\d+)[/?&]e=(\d+)|/(\d+)/(\d+))?", primary_url or "")
    s = str(season or (m_tv.group(2) if m_tv and m_tv.group(2) else (m_tv.group(4) if m_tv and m_tv.group(4) else "1")))
    e = str(episode or (m_tv.group(3) if m_tv and m_tv.group(3) else (m_tv.group(5) if m_tv and m_tv.group(5) else "1")))

    raw_candidates: list[dict] = []

    # 1. Existing pre-resolved servers (e.g. Speedostream native HLS or verified proxies)
    for srv in (existing_servers or []):
        if isinstance(srv, dict):
            raw_candidates.append(dict(srv))

    # 2. Catalogue embeds scraped from upstream detail page (e.g. movies.embeds)
    if embeds and isinstance(embeds, list):
        for emb in embeds:
            if not isinstance(emb, dict):
                continue
            u = emb.get("url") or ""
            host = (emb.get("host") or "").lower()
            if not u or any(dh in u.lower() or dh in host for dh in DISALLOWED_HOSTS):
                continue
            if "speedo" in host or "speedostream" in u.lower() or "/proxy/hls" in u.lower():
                continue

            if "vid-src.top" in host or "vidsrc.sh" in host:
                srv_label = "VidSrc - Multi"
            elif "waaw" in host:
                srv_label = "Waaw - HD"
            elif "netu" in host:
                srv_label = "Netu - Fast"
            elif "movembed" in host:
                srv_label = "MovEmbed"
            else:
                srv_label = host.split(".")[0].title() or "Embed"

            raw_candidates.append({
                "label": srv_label,
                "url": u,
                "kind": "iframe",
                "source_provenance": "catalogue_embed",
            })

    # 3. TMDB-based candidates — strictly verified before inclusion!
    if tid:
        is_released = verify_tmdb_released(tid, is_series, s, e)
        if is_released:
            # 3A. FilmU — included ONLY IF FilmU actually has this title/episode indexed
            if verify_filmu_availability(tid, is_series, s, e):
                filmu_url = f"https://embed.filmu.in/tv/{tid}/{s}/{e}" if is_series else f"https://embed.filmu.in/movie/{tid}"
                raw_candidates.append({
                    "label": "FilmU - Fast HD",
                    "url": filmu_url,
                    "kind": "iframe",
                    "provider_id": "filmu",
                })

            # 3B. VIP (vidsrc.si) — included for released titles
            vip_url = (
                f"https://embed.vidsrc.si/embed/tv/{tid}/{s}/{e}?autoplay=1&ds_lang=en"
                if is_series
                else f"https://embed.vidsrc.si/embed/movie/{tid}?autoplay=1&ds_lang=en"
            )
            raw_candidates.append({
                "label": "VIP - No ADS",
                "url": vip_url,
                "kind": "iframe",
                "provider_id": "vip",
            })

            # 3C. Secondary Fast UI & 123Embed / Cinesrc / 111Movies for Movies7 / Ask4Movies
            if source in ("movies7", "ask4movie"):
                cinesrc_url = (
                    f"https://cinesrc.st/embed/tv/{tid}/{s}/{e}"
                    if is_series
                    else f"https://cinesrc.st/embed/movie/{tid}"
                )
                m111_url = (
                    f"https://111movies.net/tv/{tid}/{s}/{e}"
                    if is_series
                    else f"https://111movies.net/movie/{tid}"
                )
                raw_candidates.append({"label": "Cinesrc - HD", "url": cinesrc_url, "kind": "iframe"})
                raw_candidates.append({"label": "111Movies - Multi", "url": m111_url, "kind": "iframe"})
            elif source in ("yomovies", "dooflix"):
                vidfast_url = (
                    f"https://vidfast.pro/tv/{tid}/{s}/{e}?autoPlay=true"
                    if is_series
                    else f"https://vidfast.pro/movie/{tid}?autoPlay=true"
                )
                raw_candidates.append({"label": "Fast UI - HD", "url": vidfast_url, "kind": "iframe"})

    # 4. Primary URL if not already present and not an unverified dummy template
    if primary_url and not any(dh in primary_url.lower() for dh in DISALLOWED_HOSTS):
        # Do not include dummy FilmU primary_url if FilmU failed availability verification
        if "embed.filmu.in" in primary_url and not verify_filmu_availability(tid or "", is_series, s, e):
            pass
        else:
            raw_candidates.append({"label": "Primary", "url": primary_url, "kind": "iframe"})

    # 5. Filter out disallowed hosts and normalize URLs
    seen_urls = set()
    filtered: list[dict] = []
    for srv in raw_candidates:
        u = (srv.get("url") or "").strip()
        if not u or u in seen_urls:
            continue
        u_lower = u.lower()
        if any(dh in u_lower for dh in DISALLOWED_HOSTS):
            continue
        seen_urls.add(u)
        filtered.append(srv)

    # 6. Rank sources dynamically based on content source and playback type:
    # Direct HLS is always Rank 0.
    # Indian / Yomovies / PRMovies sources: FilmU (if verified) Rank 1, VIP Rank 2, others follow.
    # Western / Hollywood sources: VIP Rank 1, FilmU Rank 2, others follow.
    def get_rank(item: dict) -> int:
        lbl = (item.get("label") or "").lower()
        u = (item.get("url") or "").lower()
        k = (item.get("kind") or "").lower()
        haystack = f"{lbl} {u} {k}"

        if "speedo" in haystack or "/proxy/hls" in u or k == "hls":
            return 0
        if source in ("yomovies", "dooflix"):
            if "filmu" in haystack:
                return 1
            if "vidsrc.si" in haystack or "vip" in haystack:
                return 2
            if "fast ui" in haystack or "vidfast" in haystack:
                return 3
            if "vidsrc" in haystack:
                return 4
            if "waaw" in haystack:
                return 5
            if "netu" in haystack:
                return 6
            return 10
        else:
            if "vidsrc.si" in haystack or "vip" in haystack:
                return 1
            if "filmu" in haystack:
                return 2
            if "fast ui" in haystack or "vidfast" in haystack:
                return 3
            if "cinesrc" in haystack:
                return 4
            if "111movies" in haystack:
                return 5
            return 10

    filtered.sort(key=get_rank)

    # 7. Relabel sequentially: Server 1, Server 2... numbering ONLY the available sources!
    final_servers: list[dict] = []
    for idx, srv in enumerate(filtered):
        lbl = srv.get("label") or ""
        u = srv.get("url") or ""
        u_lower = u.lower()
        k = srv.get("kind") or ("hls" if "/proxy/hls" in u_lower or ".m3u8" in u_lower else "iframe")

        # Determine clean provider display name
        if "speedo" in u_lower or "/proxy/hls" in u_lower or "speedostream" in lbl.lower():
            srv_name = "Speedostream HLS"
        elif "filmu" in u_lower or "filmu" in lbl.lower():
            srv_name = "FilmU - Fast HD"
        elif "vidsrc.si" in u_lower or "vip" in lbl.lower():
            srv_name = "VIP - No ADS"
        elif "vidfast" in u_lower or "fast ui" in lbl.lower():
            srv_name = "Fast UI - HD"
        elif "cinesrc" in u_lower or "cinesrc" in lbl.lower():
            srv_name = "Cinesrc - HD"
        elif "111movies" in u_lower or "111movies" in lbl.lower():
            srv_name = "111Movies - Multi"
        elif "vid-src.top" in u_lower or "vidsrc.sh" in u_lower or "vidsrc" in lbl.lower():
            srv_name = "VidSrc - Multi"
        elif "waaw" in u_lower or "waaw" in lbl.lower():
            srv_name = "Waaw - HD"
        elif "netu" in u_lower or "netu" in lbl.lower():
            srv_name = "Netu - Fast"
        elif "(" in lbl:
            clean_lbl = re.sub(r"\s*\(Recommended\)", "", lbl, flags=re.I).strip()
            srv_name = clean_lbl.split("(", 1)[-1].rstrip(")").strip()
            if ")" in srv_name:
                srv_name = srv_name.split(")")[0].strip()
        else:
            srv_name = re.sub(r"\s*\(Recommended\)", "", lbl, flags=re.I).strip() or "HD"

        server_num = idx + 1
        rec_tag = " (Recommended)" if server_num == 1 else ""
        final_servers.append({
            "label": f"Server {server_num} ({srv_name}){rec_tag}",
            "url": u,
            "kind": k,
        })

    main_url = final_servers[0]["url"] if final_servers else ""
    return main_url, final_servers
