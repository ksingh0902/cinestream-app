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
                {"label": "Server 1 (FilmU - Fast HD) (Recommended)", "url": f"https://embed.filmu.in/tv/{tid}/{s}/{e}", "kind": "iframe"},
                {"label": "Server 2 (VIP - No ADS)", "url": f"https://embed.vidsrc.si/embed/tv/{tid}/{s}/{e}?autoplay=1&ds_lang=en", "kind": "iframe"},
                {"label": "Server 3 (Fast UI - HD)", "url": f"https://vidfast.pro/tv/{tid}/{s}/{e}?autoPlay=true", "kind": "iframe"},
                {"label": "Server 4 (123Embed - Multi)", "url": f"https://play2.123embed.net/tv/{tid}/{s}/{e}", "kind": "iframe"},
            ]
    elif tid:
        candidate_servers = [
            {"label": "Server 1 (FilmU - Fast HD) (Recommended)", "url": f"https://embed.filmu.in/movie/{tid}", "kind": "iframe"},
            {"label": "Server 2 (VIP - No ADS)", "url": f"https://embed.vidsrc.si/embed/movie/{tid}?autoplay=1&ds_lang=en", "kind": "iframe"},
            {"label": "Server 3 (Fast UI - HD)", "url": f"https://vidfast.pro/movie/{tid}?autoPlay=true", "kind": "iframe"},
            {"label": "Server 4 (123Embed - Multi)", "url": f"https://play2.123embed.net/movie/{tid}", "kind": "iframe"},
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
        if "123embed" in u:
            return 3
        if "vidup" in u:
            return 4
        if "vidrock" in u:
            return 5
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
        all_servers.append({"label": "Primary", "url": primary_url, "kind": "iframe"})

    # Sort all servers so FilmU is ALWAYS index 0, and VIP-no ADS is ALWAYS index 1
    all_servers.sort(key=_existing_rank)

    seen_urls = set()
    final_servers = []

    # Exclude dead/ad-heavy hosts
    disallowed_hosts = ("vidlink.pro", "videasy.to", "vidcore.org", "vidsrc.pm", "2embed.cc", "primesrc.me")

    for srv in all_servers:
        u = srv.get("url") if isinstance(srv, dict) else srv
        if u:
            u = _adjust_ep(u)
        if u and u not in seen_urls and not any(dh in u.lower() for dh in disallowed_hosts):
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
            elif "vidup" in u_lower:
                srv_name = "VidUp"
            elif "vidrock" in u_lower:
                srv_name = "VidRock"
            elif "(" in lbl:
                srv_name = lbl.split("(", 1)[-1].rstrip(")")
            else:
                srv_name = lbl or "HD"

            idx = len(final_servers) + 1
            rec_tag = " (Recommended)" if idx == 1 else ""
            final_servers.append({
                "label": f"Server {idx} ({srv_name}){rec_tag}",
                "url": u,
                "kind": srv.get("kind", "iframe") if isinstance(srv, dict) else "iframe",
            })

    main_url = final_servers[0]["url"] if final_servers else primary_url
    return main_url, final_servers
