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
    (VidSrc, 2Embed, Videasy, VidFast, etc.) based on TMDB ID extracted from URL.
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
                {"label": "Server 1 (VIP - No ADS)", "url": f"https://embed.vidsrc.si/embed/tv/{tid}/{s}/{e}?autoplay=1&ds_lang=en"},
                {"label": "Server 2 (Fast UI - HD)", "url": f"https://vidfast.pro/tv/{tid}/{s}/{e}?autoPlay=true"},
                {"label": "Server 3 (FilmU - Fast HD)", "url": f"https://embed.filmu.in/tv/{tid}/{s}/{e}"},
                {"label": "Server 4 (123Embed - Multi)", "url": f"https://play2.123embed.net/tv/{tid}/{s}/{e}"},
                {"label": "Server 5 (Videasy)", "url": f"https://player.videasy.to/tv/{tid}/{s}/{e}"},
                {"label": "Server 6 (VidCore)", "url": f"https://vidcore.org/embed/tv/{tid}/{s}/{e}"},
                {"label": "Server 7 (VidSrc - Fast)", "url": f"https://vidsrc.pm/embed/tv/{tid}/{s}/{e}"},
                {"label": "Server 8 (2Embed - HD)", "url": f"https://www.2embed.cc/embedtv/{tid}&s={s}&e={e}"},
                {"label": "Server 9 (VidUp)", "url": f"https://vidup.to/tv/{tid}/{s}/{e}?autoPlay=true"},
            ]
    elif tid:
        candidate_servers = [
            {"label": "Server 1 (VIP - No ADS)", "url": f"https://embed.vidsrc.si/embed/movie/{tid}?autoplay=1&ds_lang=en"},
            {"label": "Server 2 (Fast UI - HD)", "url": f"https://vidfast.pro/movie/{tid}?autoPlay=true"},
            {"label": "Server 3 (FilmU - Fast HD)", "url": f"https://embed.filmu.in/movie/{tid}"},
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
        if "vidsrc.si" in u or "vip" in lbl:
            return 0
        if "vidfast" in u or "fast ui" in lbl:
            return 1
        if "vidup" in u:
            return 2
        if "vidrock" in u:
            return 3
        if "123embed" in u:
            return 4
        if "2embed" in u:
            return 5
        if "vidsrc.mov" in u or "vidsrc.fyi" in u:
            return 6
        return 7

    sorted_existing = sorted(servers, key=_existing_rank) if servers else []

    seen_urls = set()
    final_servers = []

    def _adjust_ep(u: str) -> str:
        if not (is_series or m_tv or season or episode) or not tid:
            return u
        if "/movie/" in u and ("vidfast" in u or "vidup" in u or "vidsrc.si" in u):
            u = u.replace(f"/movie/{tid}", f"/tv/{tid}/{s}/{e}")
        u = re.sub(rf"/tv/{tid}(?:/\d+/\d+)?", f"/tv/{tid}/{s}/{e}", u)
        if "2embed" in u:
            u = re.sub(r"&s=\d+&e=\d+", f"&s={s}&e={e}", u)
        return u

    # 1. Existing verified servers (VIP - No ADS first, Fast UI second)
    for srv in sorted_existing:
        u = srv.get("url") if isinstance(srv, dict) else srv
        if u:
            u = _adjust_ep(u)
        if u and u not in seen_urls and "vidlink.pro" not in u:
            seen_urls.add(u)
            lbl = srv.get("label") if isinstance(srv, dict) else ""
            srv_name = lbl.split("(", 1)[-1].rstrip(")") if "(" in lbl else "HD"
            final_servers.append({"label": f"Server {len(final_servers)+1} ({srv_name})", "url": u})

    # 2. Candidate generic servers
    for srv in candidate_servers:
        u = srv["url"]
        if u not in seen_urls and "vidlink.pro" not in u:
            seen_urls.add(u)
            srv_name = srv["label"].split("(", 1)[-1].rstrip(")") if "(" in srv["label"] else "HD"
            final_servers.append({"label": f"Server {len(final_servers)+1} ({srv_name})", "url": u})

    # 3. Ensure original primary_url is in the list if not broken
    if primary_url and primary_url not in seen_urls and "vidlink.pro" not in primary_url:
        final_servers.append({"label": f"Server {len(final_servers)+1} (Primary)", "url": primary_url})

    main_url = final_servers[0]["url"] if final_servers else primary_url
    return main_url, final_servers
