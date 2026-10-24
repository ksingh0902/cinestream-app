"""HTML -> dicts. Stores ABSOLUTE embed URLs so host changes are free (R3)."""
from __future__ import annotations

import re
from typing import Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from config import SITE_MIRRORS

# captures host + code of any embed player, whatever domain it lives on
EMBED_RE = re.compile(r'https?://([^/"\'\s]+)/embed-([a-z0-9]+)\.html', re.I)
M3U8_RE  = re.compile(r'sources\s*:\s*\[\s*\{\s*file\s*:\s*"([^"]+\.m3u8[^"]*)"')
DUR_RE   = re.compile(r'duration\s*:\s*"([\d.]+)"')
POSTER_RE= re.compile(r'image\s*:\s*"([^"]+)"')


def _t(n) -> str: return n.get_text(" ", strip=True) if n else ""


def parse_listing(html: str, base: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for node in soup.select("div.ml-item, article.item, div.items .item"):
        a = node.find("a", href=True)
        if not a:
            continue
        url = urljoin(base, a["href"])
        if url in seen:
            continue
        seen.add(url)
        title = (_t(node.select_one(".mli-info h2, h3, h2, .entry-title"))
                 or a.get("title") or a.get_text(" ", strip=True))
        if not title:
            continue
        img = node.find("img")
        poster = urljoin(base, (img.get("data-original") or img.get("data-src")
                                or img.get("src") or "") if img else "")
        out.append({
            "title": title, "url": url, "poster": poster,
            "quality": _t(node.select_one(".mli-quality, .quality, .label")),
            "imdb": _t(node.select_one(".jt-imdb, .imdb")),
            "year": _t(node.select_one("a[href*='/release-year/']")),
            "genres": [a.get_text(strip=True) for a in node.select("a[href*='/genre/']")],
            "is_series": 1 if "/series/" in url else 0,
        })
    return out


def parse_pagination(html: str, base: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    nxt = soup.select_one("a.next, .next.page-numbers, a[rel='next']")
    return urljoin(base, nxt["href"]) if nxt and nxt.get("href") else None


def parse_detail(html: str, url: str) -> Dict:
    soup = BeautifulSoup(html, "lxml")
    info: Dict = {"url": url, "title": _t(soup.select_one("h1, .mvic-desc h3, .entry-title")),
                  "poster": "", "synopsis": _t(soup.select_one(".mvic-desc .desc p, .f-desc")),
                  "genres": [], "actors": [], "director": [], "country": [],
                  "year": None, "duration": None, "quality": None, "imdb": None,
                  "embeds": [], "downloads": []}

    og = soup.select_one("meta[property='og:image']")
    if og and og.get("content"):
        info["poster"] = og["content"]

    for p in soup.select(".mvic-info p, .mvici-left p, .mvici-right p"):
        lab = p.find("strong") or p.find("b")
        if not lab:
            continue
        key = lab.get_text(strip=True).rstrip(":").lower()
        links = [a.get_text(strip=True) for a in p.select("a")]
        val = p.get_text(" ", strip=True).split(":", 1)[-1].strip()
        if key.startswith("genre"):            info["genres"] = links or [val]
        elif key.startswith(("actor", "star")):info["actors"] = links or [val]
        elif key.startswith("director"):       info["director"] = links or [val]
        elif key.startswith("country"):        info["country"] = links or [val]
        elif key.startswith(("release","year")):info["year"] = links[0] if links else val
        elif key.startswith("duration"):       info["duration"] = val
        elif key.startswith("quality"):        info["quality"] = val
        elif key.startswith("imdb"):           info["imdb"] = val

    # R3: absolute embed URLs discovered anywhere on the page
    seen = set()
    for m in EMBED_RE.finditer(html):
        host, code = m.group(1), m.group(2)
        if code in seen:
            continue
        seen.add(code)
        info["embeds"].append({"code": code, "host": host, "url": m.group(0)})

    for a in soup.select("#list-dl a.lnk-lnk"):
        info["downloads"].append({
            "url": a.get("href"),
            "server": _t(a.select_one(".serv_tit")) or None,
            "language": _t(a.select_one(".lang_tit")) or None,
        })
    return info


def parse_embed(html: str) -> Dict | None:
    """Signed master playlist + duration from an embed page."""
    m = M3U8_RE.search(html)
    if not m:
        return None
    d, p = DUR_RE.search(html), POSTER_RE.search(html)
    return {"hls": m.group(1).replace("\\/", "/"),
            "duration_s": float(d.group(1)) if d else None,
            "poster": p.group(1) if p else None}
