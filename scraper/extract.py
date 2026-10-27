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


EROTIC_REGEX = re.compile(
    r"\b("
    # Explicit Hot Series / erotic channels and app originals
    r"ullu(?:[\s_-]*originals?)?|alt\s*balaji|altbalaji|kooku|primeshots|prime\s+shots|primeplay|prime\s+play|"
    r"woow(?:[\s_-]*originals?)?|nuefliks|moodx|besharams\b|besharam\s+(?:originals?|app)|"
    r"feneo(?:movies)?|gemplex|boom\s*movies|ek\s+night\s+show|"
    r"hootzy|bamboo\s*flix|eight\s*shots|banana\s*prime|chikoo\s*flix|cinemadosti|cliff\s*movies|"
    r"flixsks\s*movies|balloons\s+(?:originals?|app)|piliflix|i-entertainment|i\s+entertainment|hothit(?:films)?|glamheart|"
    r"fliz(?:movies)?|hunters?\s+(?:originals?|app)|gupchup|gup\s*chup|primeflix|hot\s*masti|masti\s*prime|lootlo\s+(?:originals?|app)|"
    r"big\s*movie\s*zoo|11up(?:movies)?|hot\s*prime|world\s*prime|"
    r"bigshots|big\s+shots|hotx|hotshots|hot\s+shots|cineprime|cine\s+prime|"
    r"rabbit\s+movies?|rabbit\s+original|voovi|"
    r"redprime|red\s+prime|feelit|yessma|jalva|huntcinema|mastiplay|bulbulplay|kaddu|"
    r"desiprime|atrangii|jugnutv|tempt(?:\s+originals?|\s+app)?|honeymoon\s+couples|"
    r"hot\s+series|hot\s+web\s*series|softcore|adult\s+series|adult\s+web\s*series|"
    r"erotic\s+movies?|erotic\s+web\s*series|"
    r"hotx\s+originals?\s+uncut|\(uncut\)|\[uncut\]"
    r")\b",
    re.I
)


def is_erotic_content(item: dict) -> bool:
    """Strictly checks whether an item is erotic/softcore or from erotic channels

    (Ullu, PrimePlay, WOOW, Nuefliks, MoodX, Hotshots, Fliz, Hunters, Kooku, etc.).
    Mainstream 18+ titles (Action, Drama, Thriller like Game of Thrones, Person of Interest,
    House of the Dragon, The Boys, etc.) return False (allowed).
    """
    title = str(item.get("title") or "")
    url = str(item.get("url") or item.get("detail_url") or "")
    synopsis = str(item.get("synopsis") or "")
    genres = item.get("genres") or []
    if isinstance(genres, list):
        genres_str = " ".join(str(g) for g in genres)
    else:
        genres_str = str(genres)

    # Category and URL fast-checks
    url_l = url.lower()
    genres_l = genres_str.lower()
    if "/hot-series" in url_l or "/erotic" in url_l:
        return True
    if "erotic movies" in genres_l or "hot series" in genres_l:
        return True

    full_text = f"{title} {url} {genres_str} {synopsis}"
    return bool(EROTIC_REGEX.search(full_text))


def _t(n) -> str: return n.get_text(" ", strip=True) if n else ""


def parse_listing(html: str, base: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for node in soup.select("div.ml-item, a.ml-item, .ml-item, article.item, div.items .item"):
        a = node if node.name == "a" else node.find("a", href=True)
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
        genres = [a_g.get_text(strip=True) for a_g in node.select("a[href*='/genre/']")]
        title_l = title.lower()
        genres_l = [genre.lower() for genre in genres]
        out.append({
            "title": title, "url": url, "poster": poster,
            "quality": _t(node.select_one(".mli-quality, .quality, .label")),
            "imdb": _t(node.select_one(".jt-imdb, .imdb")),
            "year": _t(node.select_one("a[href*='/release-year/']")),
            "genres": genres,
            "is_series": 1 if (
                "/series/" in url or "/episode/" in url or "web series" in genres_l or "tv shows" in genres_l
                or "season" in title_l or "episode" in title_l
                or bool(re.search(r"\bs\d+\b|\be\d+\b", title_l))
            ) else 0,
            "is_hindi_dubbed": 1 if (
                "hindi dubbed" in title_l or "dual audio" in title_l
                or any("dub" in genre or "dual" in genre for genre in genres_l)
            ) else 0,
        })
    return out


def parse_pagination(html: str, base: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    nxt = soup.select_one("a.next, .next.page-numbers, a[rel='next']")
    if nxt and nxt.get("href"):
        return urljoin(base, nxt["href"])

    # YoMovies uses numeric links (`a.page.larger`) without a semantic Next link.
    current = 1
    current_node = soup.select_one(".wp-pagenavi .current, .pagination .current, span.current")
    if current_node:
        match = re.search(r"\d+", current_node.get_text(" ", strip=True))
        if match:
            current = int(match.group())
    numeric_links = []
    for anchor in soup.select("a.page.larger, .wp-pagenavi a.page, .pagination a"):
        text = anchor.get_text(" ", strip=True)
        href = anchor.get("href")
        if href and text.isdigit() and int(text) > current:
            numeric_links.append((int(text), urljoin(base, href)))
    return min(numeric_links, default=(0, None))[1]


def parse_detail(html: str, url: str) -> Dict:
    soup = BeautifulSoup(html, "lxml")
    title = (
        _t(soup.select_one(".mvic-desc h3, .mvic-desc h1, .mvic-desc h2, h1.entry-title, .entry-title"))
        or _t(soup.select_one(".breadcrumb li:last-child"))
        or _t(soup.select_one("h1"))
    )
    is_series = 1 if (
        "/series/" in url or "/episode/" in url or "season" in title.lower() or "episode" in title.lower()
    ) else 0

    ep_links = [urljoin(url, a["href"]) for a in soup.select("a[href*='/episode/']") if a.get("href")]
    if ep_links:
        is_series = 1

    info: Dict = {"url": url, "title": title,
                  "poster": "", "synopsis": _t(soup.select_one(".mvic-desc .desc p, .f-desc")),
                  "genres": [], "actors": [], "director": [], "country": [],
                  "year": None, "duration": None, "quality": None, "imdb": None,
                  "is_series": is_series, "episodes": ep_links,
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

    # R3: absolute embed URLs (Speedostream + Vidsrc / player iframes)
    seen = set()
    for m in EMBED_RE.finditer(html):
        host, code = m.group(1), m.group(2)
        if code in seen:
            continue
        seen.add(code)
        info["embeds"].append({"code": code, "host": host, "url": m.group(0), "type": "speedo"})

    for ifr in soup.select("#content-embed iframe, .movieplay iframe, #player2 iframe, iframe"):
        src = (ifr.get("src") or ifr.get("data-src") or "").strip()
        if not src or "youtube.com" in src or "youtu.be" in src:
            continue
        bad_domains = ["twitter.com", "x.com", "facebook.com", "instagram.com", "disqus.com", "histats.com", "doubleclick", "googletag"]
        if any(b in src.lower() for b in bad_domains):
            continue
        if src.startswith("//"):
            src = "https:" + src
        m_speedo = EMBED_RE.search(src)
        if m_speedo:
            code = m_speedo.group(2)
            if code not in seen:
                seen.add(code)
                info["embeds"].append({"code": code, "host": m_speedo.group(1), "url": src, "type": "speedo"})
            continue
        if src in seen:
            continue
        seen.add(src)
        host = src.split("/")[2] if "://" in src else "vidsrc"
        m_imdb = re.search(r'(?:imdb=|/)(tt\d+)', src)
        code = m_imdb.group(1) if m_imdb else "embed"
        info["embeds"].append({"code": code, "host": host, "url": src, "type": "embed"})

    # Fallback to IMDb ID if present in page text/meta
    m_page_imdb = re.search(r'tt\d{6,}', html)
    if m_page_imdb and not any(e.get("code", "").startswith("tt") for e in info["embeds"]):
        imdb_code = m_page_imdb.group(0)
        info["embeds"].append({
            "code": imdb_code,
            "host": "vidsrc.sh",
            "url": f"https://vidsrc.sh/embed/movie?imdb={imdb_code}",
            "type": "embed"
        })

    # Fallback to TMDB ID if present in embeds or page text
    m_tmdb = re.search(r'(?:tmdb=|/tv/|/movie/)(\d+)', html)
    if m_tmdb:
        info["tmdb_id"] = m_tmdb.group(1)

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
