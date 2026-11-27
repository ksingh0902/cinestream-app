"""Catalog scraper & parser for FlixMovie (https://flixmovie.cc)."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Iterator, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..base import MediaItem

logger = logging.getLogger("flixmovie.catalog")

FLIXMOVIE_BASE = "https://flixmovie.cc"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_YEAR_RE = re.compile(r"\((\d{4})\)\s*$")
_ANY_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_TMDB_RE = re.compile(r"(?:tmdb[_-]?id|data-id|movie_id)[\"':=\s]+(\d+)", re.I)


def _clean_poster(raw: Optional[str], base_url: str) -> Optional[str]:
    if not raw:
        return None
    u = raw.strip()
    if not u or "logo.png" in u or u.startswith("/assets/") or u.startswith("data:"):
        return None
    if u.startswith("//"):
        return "https:" + u
    return urljoin(base_url, u)


def parse_listing(html: str, base_url: str = FLIXMOVIE_BASE) -> list[MediaItem]:
    """Parse FlixMovie listing pages (/home, /movie, /tv-show, /top-imdb) into MediaItems."""
    soup = BeautifulSoup(html or "", "lxml")
    out: list[MediaItem] = []
    seen_ids: set[str] = set()

    # 1. Standard grid/carousel cards (a.bf-card)
    for a in soup.select("a.bf-card"):
        href = (a.get("href") or "").strip()
        if not href or not ("/watch/movie-" in href or "/watch/tv-" in href):
            continue
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        if not slug or slug in seen_ids:
            continue

        raw_title = (a.get("title") or "").strip()
        name_el = a.select_one(".bf-card__name")
        if name_el and name_el.get_text(strip=True):
            raw_title = name_el.get_text(strip=True)
        if not raw_title:
            continue

        ym = _YEAR_RE.search(raw_title)
        year = int(ym.group(1)) if ym else None
        clean_title = _YEAR_RE.sub("", raw_title).strip()
        clean_title = re.sub(r"\s*-\s*Season\s*\d+.*$", "", clean_title, flags=re.I).strip()
        if not clean_title:
            continue

        is_series = "/watch/tv-" in href
        img = a.select_one("img.bf-card__img") or a.select_one("img")
        poster = _clean_poster((img.get("data-src") or img.get("src")) if img else None, base_url)

        genre_el = a.select_one(".bf-card__genre")
        raw_genres = genre_el.get_text(strip=True) if genre_el else ""
        genres_list = [g.strip() for g in raw_genres.split(",") if g.strip()]

        rating: Optional[float] = None
        rating_el = a.select_one(".bf-card__rating, .imdb, .rating")
        if rating_el:
            rm = re.search(r"(\d+(?:\.\d+)?)", rating_el.get_text())
            if rm:
                try:
                    rating = float(rm.group(1))
                except ValueError:
                    pass

        seen_ids.add(slug)
        out.append(
            MediaItem(
                source="flixmovie",
                source_id=slug,
                title=clean_title,
                year=year,
                rating=rating,
                genres=json.dumps(genres_list) if genres_list else "[]",
                poster_url=poster,
                detail_url=urljoin(base_url, href),
                is_series=is_series,
                player_kind="iframe",
            )
        )

    # 2. Featured hero slides on /home (.detail + a.watch-btn)
    for detail_box in soup.select(".detail"):
        btn = detail_box.select_one("a.watch-btn[href]")
        if not btn:
            continue
        href = (btn.get("href") or "").strip()
        if not href or not ("/watch/movie-" in href or "/watch/tv-" in href):
            continue
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        if not slug or slug in seen_ids:
            continue

        title_el = detail_box.select_one(".title, h2, h1")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        if not title:
            continue

        meta_text = detail_box.select_one(".metadata")
        year = None
        rating = None
        if meta_text:
            ym = _ANY_YEAR_RE.search(meta_text.get_text(" ", strip=True))
            if ym:
                year = int(ym.group(1))
            imdb_el = meta_text.select_one(".IMDb, .imdb")
            if imdb_el:
                rm = re.search(r"(\d+(?:\.\d+)?)", imdb_el.get_text(" ", strip=True))
                if rm:
                    try:
                        rating = float(rm.group(1))
                    except ValueError:
                        pass

        genres_list = [g.get_text(strip=True) for g in detail_box.select(".genre a") if g.get_text(strip=True)]
        desc_el = detail_box.select_one(".description")
        synopsis = desc_el.get_text(" ", strip=True) if desc_el else ""

        seen_ids.add(slug)
        out.append(
            MediaItem(
                source="flixmovie",
                source_id=slug,
                title=title,
                year=year,
                rating=rating,
                genres=json.dumps(genres_list) if genres_list else "[]",
                synopsis=synopsis,
                detail_url=urljoin(base_url, href),
                is_series=("/watch/tv-" in href),
                player_kind="iframe",
            )
        )

    return out


def parse_detail(html: str, detail_url: str, base_url: str = FLIXMOVIE_BASE) -> dict:
    """Extract TMDb ID, synopsis, poster, year, and genres from a FlixMovie detail page."""
    soup = BeautifulSoup(html or "", "lxml")
    info: dict = {"detail_url": detail_url, "tmdb_id": None, "synopsis": "", "poster_url": None, "year": None, "genres": []}

    m_tmdb = _TMDB_RE.search(html or "")
    if m_tmdb:
        try:
            info["tmdb_id"] = int(m_tmdb.group(1))
        except ValueError:
            pass

    desc_meta = soup.select_one("meta[name='description'], meta[property='og:description']")
    if desc_meta and desc_meta.get("content"):
        info["synopsis"] = str(desc_meta["content"]).strip()

    og_img = soup.select_one("meta[property='og:image']")
    if og_img and og_img.get("content"):
        info["poster_url"] = _clean_poster(str(og_img["content"]), base_url)

    genres = [a.get_text(strip=True) for a in soup.select(".genre a, a[href^='/genre/']") if a.get_text(strip=True)]
    if genres:
        # Preserve unique order, capped to reasonable count for detail tags
        seen_g: set[str] = set()
        uniq_g: list[str] = []
        for g in genres[:8]:
            if g.lower() not in seen_g:
                seen_g.add(g.lower())
                uniq_g.append(g)
        info["genres"] = uniq_g

    return info


def iter_catalog(
    *,
    max_pages: int = 2,
    base_url: str = FLIXMOVIE_BASE,
    delay: float = 0.5,
    session: Optional[requests.Session] = None,
) -> Iterator[MediaItem]:
    """Yield unique MediaItems from FlixMovie /home, /movie, /tv-show, and /top-imdb."""
    base = base_url.rstrip("/")
    urls = [f"{base}/home", f"{base}/top-imdb"]
    for p in range(1, max(1, max_pages) + 1):
        urls.append(f"{base}/movie" if p == 1 else f"{base}/movie?page={p}")
        urls.append(f"{base}/tv-show" if p == 1 else f"{base}/tv-show?page={p}")

    owns_session = session is None
    sess = session if session is not None else requests.Session()
    headers = {"User-Agent": DEFAULT_UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    seen: set[str] = set()

    try:
        for idx, url in enumerate(urls):
            if idx > 0 and delay > 0:
                time.sleep(delay)
            try:
                r = sess.get(url, headers=headers, timeout=15, allow_redirects=True)
                if r.status_code != 200 or "just a moment" in (r.text or "").lower()[:600]:
                    logger.warning("FlixMovie page skipped (status=%s): %s", r.status_code, url)
                    continue
                for item in parse_listing(r.text, base_url=base):
                    if item.source_id not in seen:
                        seen.add(item.source_id)
                        yield item
            except Exception as exc:
                logger.warning("FlixMovie fetch error on %s: %s", url, exc)
    finally:
        if owns_session:
            sess.close()
