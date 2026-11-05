from __future__ import annotations

import re


def enrich_stream_servers(
    primary_url: str,
    is_series: bool = False,
    existing_servers: list | None = None,
    tmdb_id: str | None = None,
    season: int | str | None = None,
    episode: int | str | None = None,
) -> tuple[str, list[dict]]:
    """Enriches an iframe embed URL with fast, reliable, ad-free fallback servers
    (FilmU, VidSrc VIP, Fast UI, Videasy, etc.) based on TMDB ID extracted from URL.
    Server 1 (Default): FilmU - Fast HD
    Server 2 (Second default): VIP - No ADS
    """
    servers = list(existing_servers or [])

    tid = str(tmdb_id) if tmdb_id else None
    if not tid and primary_url:
        m_id = re.search(r"(?:/movie/|/embed/|/embedtv/|/tv/|-)(\d{3,9})", primary_url)
        if m_id:
            tid = m_id.group(1)

    m_tv = re.search(r"/(?:tv|embedtv)/(\d+)(?:[/?&]s=(\d+)[/?&]e=(\d+)|/(\d+)/(\d+))?", primary_url or "")

    candidate_servers = []
    if is_series or m_tv or season or episode:
        s = str(season or (m_tv.group(2) if m_tv and m_tv.group(2) else (m_tv.group(4) if m_tv and m_tv.group(4) else "1")))
        e = str(episode or (m_tv.group(3) if m_tv and m_tv.group(3) else (m_tv.group(5) if m_tv and m_tv.group(5) else "1")))
        if tid:
            candidate_servers = [
                {"label": "Server 1 (FilmU - Fast HD)", "url": f"https://embed.filmu.in/tv/{tid}/{s}/{e}"},
                {"label": "Server 2 (VIP - No ADS)", "url": f"https://embed.vidsrc.si/embed/tv/{tid}/{s}/{e}?autoplay=1&ds_lang=en"},
                {"label": "Server 3 (Fast UI - HD)", "url": f"https://vidfast.pro/tv/{tid}/{s}/{e}?autoPlay=true"},
                {"label": "Server 4 (123Embed - Multi)", "url": f"https://play2.123embed.net/tv/{tid}/{s}/{e}"},
                {"label": "Server 5 (Videasy)", "url": f"https://player.videasy.to/tv/{tid}/{s}/{e}"},
                {"label": "Server 6 (VidCore)", "url": f"https://vidcore.org/embed/tv/{tid}/{s}/{e}"},
                {"label": "Server 7 (VidSrc - Fast)", "url": f"https://vidsrc.pm/embed/tv/{tid}/{s}/{e}"},
                {"label": "Server 8 (2Embed - HD)", "url": f"https://www.2embed.cc/embedtv/{tid}&s={s}&e={e}"},
                {"label": "Server 9 (VidUp)", "url": f"https://vidup.to/tv/{tid}/{s}/{e}?autoPlay=true"},
            ]
    elif tid:
        candidate_servers = [
            {"label": "Server 1 (FilmU - Fast HD)", "url": f"https://embed.filmu.in/movie/{tid}"},
            {"label": "Server 2 (VIP - No ADS)", "url": f"https://embed.vidsrc.si/embed/movie/{tid}?autoplay=1&ds_lang=en"},
            {"label": "Server 3 (Fast UI - HD)", "url": f"https://vidfast.pro/movie/{tid}?autoPlay=true"},
            {"label": "Server 4 (123Embed - Multi)", "url": f"https://play2.123embed.net/movie/{tid}"},
            {"label": "Server 5 (Videasy)", "url": f"https://player.videasy.to/movie/{tid}"},
            {"label": "Server 6 (VidCore)", "url": f"https://vidcore.org/embed/movie/{tid}"},
            {"label": "Server 7 (VidSrc - Fast)", "url": f"https://vidsrc.pm/embed/movie/{tid}"},
            {"label": "Server 8 (2Embed - HD)", "url": f"https://www.2embed.cc/embed/{tid}"},
            {"label": "Server 9 (VidUp)", "url": f"https://vidup.to/movie/{tid}?autoPlay=true"},
        ]

    def _existing_rank(srv: dict | str) -> int:
        u = (srv.get("url") if isinstance(srv, dict) else str(srv)).lower()
        lbl = (srv.get("label") if isinstance(srv, dict) else "").lower()
        if "filmu" in u or "filmu" in lbl:
            return 0
        if "vidsrc.si" in u or "vip" in lbl:
            return 1
        if "vidfast" in u or "fast ui" in lbl:
            return 2
        if "vidup" in u:
            return 3
        if "vidrock" in u:
            return 4
        if "123embed" in u:
            return 5
        if "videasy" in u:
            return 6
        if "vidcore" in u:
            return 7
        if "2embed" in u:
            return 8
        if "vidsrc.pm" in u or "vidsrc.mov" in u or "vidsrc.fyi" in u:
            return 9
        return 10

    def _adjust_ep(u: str) -> str:
        if not (is_series or m_tv or season or episode) or not tid:
            return u
        if "/movie/" in u and ("filmu" in u or "vidfast" in u or "vidup" in u or "vidsrc.si" in u):
            u = u.replace(f"/movie/{tid}", f"/tv/{tid}/{s}/{e}")
        u = re.sub(rf"/tv/{tid}(?:/\d+/\d+)?", f"/tv/{tid}/{s}/{e}", u)
        if "2embed" in u:
            u = re.sub(r"&s=\d+&e=\d+", f"&s={s}&e={e}", u)
        return u

    all_servers = []
    # 1. Candidate servers (standard list with FilmU #1, VIP-no ADS #2)
    for srv in candidate_servers:
        all_servers.append(srv)
    # 2. Existing servers from database / scrape
    for srv in servers:
        all_servers.append(srv)
    # 3. Primary url if present
    if primary_url:
        all_servers.append({"label": "Primary", "url": primary_url})

    # Sort all servers so FilmU is ALWAYS index 0, and VIP-no ADS is ALWAYS index 1
    all_servers.sort(key=_existing_rank)

    seen_urls = set()
    final_servers = []

    for srv in all_servers:
        u = srv.get("url") if isinstance(srv, dict) else srv
        if u:
            u = _adjust_ep(u)
        if u and u not in seen_urls and "vidlink.pro" not in u:
            seen_urls.add(u)
            lbl = srv.get("label") if isinstance(srv, dict) else ""
            u_lower = u.lower()
            if "filmu" in u_lower:
                srv_name = "FilmU - Fast HD"
            elif "vidsrc.si" in u_lower or "vip" in lbl.lower():
                srv_name = "VIP - No ADS"
            elif "vidfast" in u_lower or "fast ui" in lbl.lower():
                srv_name = "Fast UI - HD"
            elif "123embed" in u_lower:
                srv_name = "123Embed - Multi"
            elif "videasy" in u_lower:
                srv_name = "Videasy"
            elif "vidcore" in u_lower:
                srv_name = "VidCore"
            elif "vidsrc.pm" in u_lower:
                srv_name = "VidSrc - Fast"
            elif "2embed" in u_lower:
                srv_name = "2Embed - HD"
            elif "vidup" in u_lower:
                srv_name = "VidUp"
            elif "(" in lbl:
                srv_name = lbl.split("(", 1)[-1].rstrip(")")
            else:
                srv_name = lbl or "HD"
            final_servers.append({"label": f"Server {len(final_servers)+1} ({srv_name})", "url": u})

    main_url = final_servers[0]["url"] if final_servers else primary_url
    return main_url, final_servers
