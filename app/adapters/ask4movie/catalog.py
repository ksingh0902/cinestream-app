from __future__ import annotations

import re
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..base import MediaItem
from .config import CFG
from .http import get

_TITLE_RE = re.compile(r"/title/(?P<slug>.+?)-(?P<tmdb>\d+)/?$", re.I)
_TYPE_RE = re.compile(r"^\s*(?P<year>\d{4})\s*·\s*(?P<kind>.+?)\s*$")
_YEAR_RE = re.compile(r"\((\d{4})\)\s*$")
_LANG_RE = re.compile(r"original\s+language\s*[:\-–]?\s*([A-Za-z][A-Za-z ()'\-]{2,40})", re.I)


def _base() -> str:
    return CFG.catalog_mirrors[0].rstrip("/")


def parse_listing(html: str) -> list[MediaItem]:
    soup = BeautifulSoup(html, "lxml")
    out: list[MediaItem] = []

    # 1. fbox.gd format (a.bf-card)
    for a in soup.select("a.bf-card"):
        href = a.get("href", "")
        if not href or not ("/watch/movie-" in href or "/watch/tv-" in href):
            continue
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        raw_title = a.get("title", "")
        name_el = a.select_one(".bf-card__name")
        if name_el and name_el.get_text(strip=True):
            raw_title = name_el.get_text(strip=True)

        ym = _YEAR_RE.search(raw_title)
        year = int(ym.group(1)) if ym else None
        clean_title = _YEAR_RE.sub("", raw_title).strip()
        clean_title = re.sub(r"\s*-\s*Season\s*\d+.*$", "", clean_title, flags=re.I).strip()

        is_series = bool("/watch/tv-" in href)
        img = a.select_one("img.bf-card__img") or a.select_one("img")
        poster = img.get("src") if img else None

        genre_el = a.select_one(".bf-card__genre")
        raw_genres = genre_el.get_text(strip=True) if genre_el else ""
        genres_list = [g.strip() for g in raw_genres.split(",") if g.strip()]
        import json
        genres_json = json.dumps(genres_list) if genres_list else "[]"

        out.append(MediaItem(
            source="ask4movie",
            source_id=slug,
            title=clean_title,
            year=year,
            genres=genres_json,
            poster_url=poster,
            detail_url=urljoin("https://fbox.gd", href),
            is_series=is_series,
            player_kind="iframe",
        ))

    # 2. ask4movietv.cyou format (article.card)
    for card in soup.select("article.card"):
        a = card.select_one("a.poster[href]") or card.select_one("h3 > a[href]")
        if not a:
            continue
        href = urljoin(_base(), a["href"])
        m = _TITLE_RE.search(href)
        if not m:
            continue

        meta = card.select_one("p")
        year = None
        kind = ""
        if meta:
            tm = _TYPE_RE.match(meta.get_text(" ", strip=True))
            if tm:
                year = int(tm.group("year"))
                kind = tm.group("kind").strip()

        is_series = bool(kind and ("series" in kind.lower() or "tv" in kind.lower()))

        img = card.select_one("img")
        rating_el = card.select_one(".rating")
        rating = None
        if rating_el:
            rm = re.search(r"(\d+(?:\.\d+)?)", rating_el.get_text())
            if rm:
                rating = float(rm.group(1))

        title_el = card.select_one("h3")
        out.append(MediaItem(
            source="ask4movie",
            source_id=m.group("slug") + "-" + m.group("tmdb"),
            title=(title_el.get_text(strip=True) if title_el else "").strip(),
            year=year,
            rating=rating,
            tmdb_id=int(m.group("tmdb")),
            poster_url=(urljoin(_base(), img["src"]) if img and img.get("src") else None),
            detail_url=href,
            is_series=is_series,
            player_kind="iframe",
        ))
    return [i for i in out if i.title]


def next_page(html: str, current: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for sel in ('link[rel="next"]', 'a[rel="next"]', "a.next", ".pagination a"):
        el = soup.select_one(sel)
        if el and el.get("href"):
            nxt = urljoin(current, el["href"])
            if nxt != current:
                return nxt

    # Sequential ?page={N} navigation
    m = re.search(r"[?&]page=(\d+)", current)
    if m:
        nxt_num = int(m.group(1)) + 1
        return re.sub(r"([?&]page=)\d+", f"\\g<1>{nxt_num}", current)
    sep = "&" if "?" in current else "?"
    return f"{current}{sep}page=2"


def crawl_listing(seed: str = "/movies/", *, max_pages: int = 0) -> Iterator[MediaItem]:
    clean_seed = seed.rstrip("/")
    page = 1
    limit = max_pages if max_pages > 0 else 50
    seen_ids: set[str] = set()

    while page <= limit:
        url = f"{_base()}{clean_seed}/?page={page}" if page > 1 else f"{_base()}{clean_seed}/"
        try:
            html = get(url).text
        except Exception:
            break
        cards = parse_listing(html)
        if not cards:
            break
        new_found = False
        for c in cards:
            if c.source_id not in seen_ids:
                seen_ids.add(c.source_id)
                new_found = True
                yield c
        if not new_found:
            break
        page += 1


def parse_language(html: str) -> tuple[str | None, str | None]:
    """Returns (language_name, iso_code). Name first, code only if we can infer it."""
    soup = BeautifulSoup(html, "lxml")
    
    # 1. dt/dd definition list
    for dt in soup.select("dt"):
        if "original language" in dt.get_text().lower():
            dd = dt.find_next_sibling("dd") or (dt.parent.select_one("dd") if dt.parent else None)
            if dd and dd.get_text(strip=True):
                return dd.get_text(strip=True), None

    # 2. Text regex
    text = soup.get_text(" ", strip=True)
    m = _LANG_RE.search(text)
    if m:
        raw = m.group(1).strip().rstrip(".,;")
        lang = raw.split()[0] if raw else None
        return lang, None

    return None, None


def enrich(item: MediaItem) -> MediaItem:
    if item.detail_url and "fbox.gd" in item.detail_url and item.poster_url:
        return item
    try:
        html = get(item.detail_url).text
    except Exception:
        return item

    soup = BeautifulSoup(html, "lxml")
    name, code = parse_language(html)

    # Optional, higher-fidelity fallback via TMDB when a key is configured
    if (not name or not code) and CFG.tmdb_api_key and item.tmdb_id:
        try:
            r = get(f"https://api.themoviedb.org/3/movie/{item.tmdb_id}",
                    params={"api_key": CFG.tmdb_api_key}, accept="application/json")
            j = r.json()
            code = code or j.get("original_language")
            name = name or j.get("original_title")
            if not item.synopsis:
                item.synopsis = (j.get("overview") or "").strip()
            if not item.poster_url and j.get("poster_path"):
                item.poster_url = f"https://image.tmdb.org/t/p/w500{j['poster_path']}"
            if j.get("runtime") and not item.duration_s:
                item.duration_s = int(j["runtime"]) * 60
        except Exception:
            pass

    item.language = name
    item.language_code = code

    # Runtime from page if available
    for dt in soup.select("dt"):
        if "runtime" in dt.get_text().lower():
            dd = dt.find_next_sibling("dd") or (dt.parent.select_one("dd") if dt.parent else None)
            if dd:
                rm = re.search(r"(\d+)\s*m", dd.get_text())
                if rm and not item.duration_s:
                    item.duration_s = int(rm.group(1)) * 60

    # Genres from page
    genres = [a.get_text(strip=True) for a in soup.select("a[href*='/genre/']")]
    if genres and not item.genres:
        item.genres = ", ".join(genres)

    if not item.synopsis:
        for sel in ("p.synopsis", ".overview", "section.synopsis p", "article p"):
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 40:
                item.synopsis = el.get_text(" ", strip=True)
                break

    return item
