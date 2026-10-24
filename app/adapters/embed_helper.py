from __future__ import annotations

import re


def enrich_stream_servers(
    primary_url: str,
    is_series: bool = False,
    existing_servers: list | None = None,
    tmdb_id: str | None = None,
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
    if is_series or m_tv:
        s = "1"
        e = "1"
        if m_tv:
            s = m_tv.group(2) or m_tv.group(4) or "1"
            e = m_tv.group(3) or m_tv.group(5) or "1"
        if tid:
            candidate_servers = [
                {"label": "Server 1 (FilmU - Fast HD)", "url": f"https://embed.filmu.in/tv/{tid}/{s}/{e}"},
                {"label": "Server 2 (123Embed - Multi)", "url": f"https://play2.123embed.net/tv/{tid}/{s}/{e}"},
                {"label": "Server 3 (Videasy)", "url": f"https://player.videasy.to/tv/{tid}/{s}/{e}"},
                {"label": "Server 4 (VidCore)", "url": f"https://vidcore.org/embed/tv/{tid}/{s}/{e}"},
                {"label": "Server 5 (VidSrc - Fast)", "url": f"https://vidsrc.pm/embed/tv/{tid}/{s}/{e}"},
                {"label": "Server 6 (2Embed - HD)", "url": f"https://www.2embed.cc/embedtv/{tid}&s={s}&e={e}"},
            ]
    elif tid:
        candidate_servers = [
            {"label": "Server 1 (FilmU - Fast HD)", "url": f"https://embed.filmu.in/movie/{tid}"},
            {"label": "Server 2 (123Embed - Multi)", "url": f"https://play2.123embed.net/movie/{tid}"},
            {"label": "Server 3 (Videasy)", "url": f"https://player.videasy.to/movie/{tid}"},
            {"label": "Server 4 (VidCore)", "url": f"https://vidcore.org/embed/movie/{tid}"},
            {"label": "Server 5 (VidSrc - Fast)", "url": f"https://vidsrc.pm/embed/movie/{tid}"},
            {"label": "Server 6 (2Embed - HD)", "url": f"https://www.2embed.cc/embed/{tid}"},
        ]

    seen_urls = set()
    final_servers = []

    # 1. Candidate servers (2Embed first, followed by VidSrc & Videasy)
    for srv in candidate_servers:
        u = srv["url"]
        if u not in seen_urls and "vidlink.pro" not in u:
            seen_urls.add(u)
            final_servers.append(srv)

    # 2. Existing servers if any (excluding broken vidlink)
    for srv in servers:
        u = srv.get("url") if isinstance(srv, dict) else srv
        if u and u not in seen_urls and "vidlink.pro" not in u:
            seen_urls.add(u)
            lbl = srv.get("label") if isinstance(srv, dict) else f"Server {len(final_servers)+1}"
            final_servers.append({"label": lbl, "url": u})

    # 3. Ensure original primary_url is in the list if not broken
    if primary_url and primary_url not in seen_urls and "vidlink.pro" not in primary_url:
        final_servers.append({"label": f"Server {len(final_servers)+1}", "url": primary_url})

    main_url = final_servers[0]["url"] if final_servers else primary_url
    return main_url, final_servers
