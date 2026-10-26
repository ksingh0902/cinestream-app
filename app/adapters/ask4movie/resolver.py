from __future__ import annotations

import difflib
import os
import re
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..base import StreamInfo
from . import fbox_gate
from .config import CFG
from .http import get

_NORM_RE = re.compile(r"[^a-z0-9 ]+")
_YEAR_RE = re.compile(r"\((\d{4})\)\s*$")
_CARD_RE = re.compile(r'<a class="bf-card"[^>]*href="([^"]+)"[^>]*title="([^"]*)"')
_EMBED_RE = re.compile(r"""["'\(](https?:)?(//[^"'\)\s]+?/(?:embed|e)/[^"'\)\s]+)["'\)]""")


def _base() -> str:
    return CFG.stream_mirrors[0].rstrip("/")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode()
    return _NORM_RE.sub(" ", text.lower()).strip()


def find_watch_url(title: str, year: int | None = None) -> str | None:
    """Search fbox /browser and pick the best title+year match."""
    base = _base()
    fbox_gate.verify(base, "/browser")
    try:
        html = get(base + "/browser", params={"keyword": title}).text
    except Exception:
        fbox_gate.invalidate(base, "/browser")
        try:
            fbox_gate.verify(base, "/browser", force=True)
            html = get(base + "/browser", params={"keyword": title}).text
        except Exception:
            return None

    want = norm(title)
    best, best_score = None, 0.0

    for href, raw_title in _CARD_RE.findall(html):
        ym = _YEAR_RE.search(raw_title)
        card_year = int(ym.group(1)) if ym else None
        card_title = _YEAR_RE.sub("", raw_title).strip()
        score = difflib.SequenceMatcher(None, want, norm(card_title)).ratio()
        if year and card_year and abs(card_year - year) <= 1:
            score += 0.25
        if "/watch/movie-" not in href:
            score -= 0.05
        if score > best_score:
            best, best_score = href, score

    if best and best_score >= 0.72:
        return urljoin(base, best)
    return None


def _absolute(base: str, src: str) -> str:
    if src.startswith("//"):
        return "https:" + src
    return urljoin(base, src)


def parse_player(html: str, page_url: str) -> StreamInfo | None:
    """Extract the player. Prefers iframe#embed-iframe, then any embed iframe,
    then an /embed/ URL found in inline JS, then data-src server pills."""
    soup = BeautifulSoup(html, "lxml")

    def _src(tag) -> str | None:
        return tag.get("src") or tag.get("data-src") or tag.get("data-embed")

    # 1. The theme's own player hook (iframe#embed-iframe)
    el = soup.select_one("iframe#embed-iframe")
    if el:
        if _src(el):
            return StreamInfo(kind="iframe", url=_absolute(page_url, _src(el)))
        
        # Check srcdoc with /api/go action
        srcdoc = el.get("srcdoc") or ""
        if 'action="/api/go"' in srcdoc or 'action=\\"/api/go\\"' in srcdoc:
            m_slug = re.search(r'name=["\']slug["\']\s+value=["\']([^"\']+)["\']', srcdoc)
            m_t = re.search(r'name=["\']t["\']\s+value=["\']([^"\']+)["\']', srcdoc)
            if m_slug:
                t_val = m_t.group(1) if m_t else "movie"
                slug_val = m_slug.group(1)

                from urllib.parse import urlparse
                parsed_p = urlparse(page_url)
                page_origin = f"{parsed_p.scheme}://{parsed_p.netloc}" if parsed_p.scheme and parsed_p.netloc else _base()

                pill_labels = {}
                for pill in soup.select(".opt-pill"):
                    pv = pill.get("value")
                    pt = pill.get_text(" ", strip=True)
                    if pv is not None and pt:
                        pill_labels[str(pv)] = pt

                dest_urls: list[dict[str, str]] = []
                for x in range(8):
                    go_url = f"{page_origin}/api/go?t={t_val}&slug={slug_val}&x={x}"
                    try:
                        r_go = get(go_url)
                        m_dest = re.search(r'url=(https?://[^"\'>\s]+)', r_go.text)
                        if m_dest:
                            clean_u = m_dest.group(1).replace("&amp;", "&")
                            if clean_u not in [d["url"] for d in dest_urls]:
                                name = pill_labels.get(str(x), "")
                                dest_urls.append({"raw_name": name, "url": clean_u})
                    except Exception:
                        pass

                if dest_urls:
                    def _rank(item: dict[str, str]) -> int:
                        u = item["url"].lower()
                        name = (item.get("raw_name") or "").lower()
                        if "vidsrc.si" in u or "vip" in name:
                            return 0
                        if "vidfast" in u:
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

                    dest_urls.sort(key=_rank)

                    servers = []
                    for i, d in enumerate(dest_urls):
                        u = d["url"]
                        u_lower = u.lower()
                        raw_name = d.get("raw_name", "")
                        if "vidsrc.si" in u_lower or "vip" in raw_name.lower():
                            lbl = f"Server {i+1} (VIP - No ADS)"
                        elif "vidfast" in u_lower:
                            lbl = f"Server {i+1} (Fast UI - HD)"
                        elif "vidup" in u_lower:
                            lbl = f"Server {i+1} (VidUp - Multi)"
                        elif "vidrock" in u_lower:
                            lbl = f"Server {i+1} (VidRock)"
                        elif "vidsrc.mov" in u_lower:
                            lbl = f"Server {i+1} (VidSrc - Mov)"
                        elif "vidsrc.fyi" in u_lower:
                            lbl = f"Server {i+1} (VidSrc - Fast)"
                        elif raw_name:
                            lbl = f"Server {i+1} ({raw_name})"
                        else:
                            lbl = f"Server {i+1}"
                        servers.append({"label": lbl, "url": u})

                    return StreamInfo(kind="iframe", url=servers[0]["url"], servers=servers)

    # 2. Any iframe that is not a tracker / self-reference
    for ifr in soup.find_all("iframe"):
        s = _src(ifr)
        if not s:
            continue
        abs_url = _absolute(page_url, s)
        host = abs_url.split("//", 1)[-1].split("/")[0]
        if host in ("fbox.gd",) or "histats" in host or "cdn-cgi" in abs_url:
            continue
        return StreamInfo(kind="iframe", url=abs_url)

    # 3. Inline JS / JSON-LD carrying an embed URL
    m = _EMBED_RE.search(html)
    if m:
        return StreamInfo(kind="iframe", url=_absolute(page_url, m.group(2)))

    # 4. Server pills (#opt-panel .opt-pill / [data-src]) -> first one + full list
    servers = []
    for pill in soup.select("#opt-panel [data-src], .server[data-src], "
                            "[data-embed], .opt-pill[data-url]"):
        u = pill.get("data-src") or pill.get("data-embed") or pill.get("data-url")
        if u:
            servers.append({"label": pill.get_text(" ", strip=True) or "Server",
                            "url": _absolute(page_url, u)})
    if servers:
        return StreamInfo(kind="iframe", url=servers[0]["url"], servers=servers)

    # 5. Raw m3u8 in the page -> source A's proxy can take it
    m3u8 = re.search(r"https?://[^\s\"']+\.m3u8[^\s\"']*", html)
    if m3u8:
        return StreamInfo(kind="hls", url=m3u8.group(0), ttl_s=CFG.player_ttl_s)

    return None


def resolve(detail_url: str) -> StreamInfo:
    """Permanent /watch/... page -> fresh playable StreamInfo."""
    # Check if detail_url contains a TMDB ID (Ask4movie style /title/slug-<id>/)
    m_tmdb = re.search(r"-(\d+)/?$", detail_url)
    if m_tmdb:
        cand = m_tmdb.group(1)
        if not (len(cand) == 4 and (cand.startswith("19") or cand.startswith("20"))):
            tid = cand
            is_tv = "/tv-" in detail_url or "/series/" in detail_url or "/show/" in detail_url
            dummy = f"https://vidsrc.pm/embed/{'tv' if is_tv else 'movie'}/{tid}" + ("/1/1" if is_tv else "")
            from ..embed_helper import enrich_stream_servers
            main_u, servers = enrich_stream_servers(dummy, is_series=is_tv, tmdb_id=str(tid))
            return StreamInfo(kind="iframe", url=main_u, servers=servers)

    base = _base()

    # Determine watch path on fbox
    if "/watch/" in detail_url:
        path = "/watch/" + detail_url.rstrip("/").rsplit("/", 1)[-1]
    else:
        # Ask4movie detail page URL, e.g. /title/avatar-19995/
        # Extract title slug to search / watch on fbox
        slug = detail_url.rstrip("/").rsplit("/", 1)[-1]
        slug_clean = re.sub(r'-\d+$', '', slug).replace('-', ' ')
        watch_url = find_watch_url(slug_clean)
        if watch_url:
            path = "/watch/" + watch_url.rstrip("/").rsplit("/", 1)[-1]
        else:
            path = f"/watch/movie-{slug}"

    for attempt in (1, 2):
        fbox_gate.verify(base, path, force=(attempt == 2))
        try:
            html = get(base + path).text
        except Exception:
            fbox_gate.invalidate(base, path)
            continue

        if "Just a quick check" in html or "id=\"__hvtok\"" in html:
            fbox_gate.invalidate(base, path)
            continue

        if CFG.debug_dump:
            os.makedirs(CFG.debug_dump, exist_ok=True)
            with open(f"{CFG.debug_dump}/watch_{path.strip('/').replace('/', '_')}.html",
                      "w", encoding="utf-8") as fh:
                fh.write(html)

        info = parse_player(html, base + path)
        if info:
            info.headers = {"Referer": base + "/", "Origin": base}
            return info

    raise RuntimeError(f"could not resolve player for {detail_url}")
