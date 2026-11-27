"""Catalog scraper & parser for MoviesDrive (https://new5.moviesdrive.cyou / https://moviesdrives.bid)."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Iterator, Optional, Sequence
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.catalogue.quality import extract_print_quality
from ..base import MediaItem

logger = logging.getLogger("moviesdrive.catalog")

MOVIESDRIVE_MIRRORS: tuple[str, ...] = (
    "https://new5.moviesdrive.cyou",
    "https://moviesdrives.bid",
)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_YEAR_RE = re.compile(r"[\[(]?\b((?:19|20)\d{2})\b[\])]?")
_SEASON_RE = re.compile(r"\b(?:season\s*\d{1,2}|s\d{1,2}\s*ep?\d+|web\s*series|series\s+\d{3,4}p)\b", re.I)
_IMDB_RE = re.compile(r"\b(tt\d{6,9})\b")
_TMDB_RE = re.compile(r"themoviedb\.org/(?:movie|tv)/(\d+)", re.I)
_TITLE_CUT_RE = re.compile(
    r"(?:"
    r"\s*[\[(]\s*(?:19|20)\d{2}\s*[\])]"
    r"|\s+\b(?:19|20)\d{2}\b"
    r"|\s+\b(?:hq-?hdtc|hdtc|hdcam|camrip|pre-?dvd|web-?dl|webrip|bluray|bdrip|hdrip|480p|720p|1080p|2160p|4k)\b"
    r"|\s+\[[^\]]*(?:hindi|english|dual|dd\d|aac|x264|x265|hevc|esub)[^\]]*\]"
    r")",
    re.I,
)

_OTT_PATTERNS = (
    ("Netflix", re.compile(r"\bnetflix\b", re.I)),
    ("Amazon Prime", re.compile(r"\b(?:amazon\s*prime|prime\s*video)\b", re.I)),
    ("Hotstar", re.compile(r"\b(?:jio\s*hotstar|hotstar)\b", re.I)),
    ("Zee5", re.compile(r"\bzee5\b", re.I)),
    ("Sony Liv", re.compile(r"\bsony\s*liv\b", re.I)),
    ("Apple TV+", re.compile(r"\bapple\s*tv\+?\b", re.I)),
)


def parse_moviesdrive_title(raw_title: str, badge_quality: str = "") -> dict:
    """Extract clean title, year, print quality, series flag, Hindi-dubbed flag, and OTT/genre tags."""
    raw = re.sub(r"\s+", " ", (raw_title or "")).strip()
    m_yr = _YEAR_RE.search(raw)
    year = int(m_yr.group(1)) if m_yr else None

    is_series = bool(_SEASON_RE.search(raw))

    # Preserve "(Season N)" if present before the year/technical tail
    m_cut = _TITLE_CUT_RE.search(raw)
    clean_title = raw[: m_cut.start()].strip(" -–|:") if m_cut else raw
    if not clean_title:
        clean_title = raw[:120]

    low = raw.lower()
    is_hindi_dubbed = any(
        k in low for k in ("hindi", "dual audio", "hindi dubbed", "hindi org", "hindi dd")
    )
    genres: list[str] = []
    if "dual audio" in low or ("hindi" in low and "english" in low):
        genres.append("Dual Audio")
    elif "hindi" in low:
        genres.append("Hindi")
    for label, pat in _OTT_PATTERNS:
        if pat.search(raw):
            genres.append(label)

    # Extract genuine print quality (CAM/HDTC/WEB-DL/BluRay/1080p/etc.)
    # MoviesDrive appends "480p | 720p | 1080p" to CAM/HDTC titles too, so check CAM/HDTC tokens first!
    badge_up = badge_quality.strip().upper()
    if badge_up in ("CAM", "HDCAM", "HDTC", "PREDVD", "TS") or re.search(
        r"\b(?:hq-?hdtc|hdtc|hdcam|camrip|pre-?dvd|dvdscr|telesync|telecine)\b", raw, re.I
    ):
        print_quality = "CAM"
    else:
        badge_norm = "1080p" if badge_up == "FHD" else badge_quality.strip()
        print_quality = extract_print_quality(raw, badge_norm) or badge_norm or ""

    return {
        "title": clean_title,
        "year": year,
        "is_series": is_series,
        "is_hindi_dubbed": is_hindi_dubbed,
        "genres": genres,
        "quality": print_quality,
    }


def _clean_poster(raw: Optional[str], base_url: str) -> Optional[str]:
    if not raw:
        return None
    u = raw.strip()
    if not u or "logo." in u.lower() or u.startswith("data:"):
        return None
    if u.startswith("//"):
        return "https:" + u
    return urljoin(base_url, u)


def parse_listing(html: str, base_url: str = MOVIESDRIVE_MIRRORS[0]) -> list[MediaItem]:
    """Parse MoviesDrive listing pages (.movies-grid a / .poster-card) into MediaItems."""
    soup = BeautifulSoup(html or "", "lxml")
    out: list[MediaItem] = []
    seen_ids: set[str] = set()

    cards = soup.select(".movies-grid a[href]") or soup.select("a:has(.poster-card)")
    for a in cards:
        href = (a.get("href") or "").strip()
        if not href:
            continue
        full_url = urljoin(base_url, href)
        slug = full_url.rstrip("/").rsplit("/", 1)[-1]
        if not slug or slug in seen_ids:
            continue

        title_el = a.select_one(".poster-title")
        img_el = a.select_one("img")
        raw_title = (
            (title_el.get_text(" ", strip=True) if title_el else "")
            or (img_el.get("alt") if img_el else "")
            or a.get_text(" ", strip=True)
        ).strip()
        if not raw_title:
            continue

        q_el = a.select_one(".poster-quality")
        badge_q = q_el.get_text(" ", strip=True) if q_el else ""
        meta = parse_moviesdrive_title(raw_title, badge_quality=badge_q)

        poster = _clean_poster(
            (img_el.get("data-src") or img_el.get("src")) if img_el else None,
            base_url,
        )

        seen_ids.add(slug)
        item = MediaItem(
            source="moviesdrive",
            source_id=slug,
            title=meta["title"],
            year=meta["year"],
            language="Hindi" if meta["is_hindi_dubbed"] else None,
            language_code="hi" if meta["is_hindi_dubbed"] else None,
            poster_url=poster,
            genres=json.dumps(meta["genres"]),
            is_series=meta["is_series"],
            detail_url=full_url,
            player_kind="iframe",
        )
        # Attach parsed print quality as extra attribute for sync upsert
        setattr(item, "quality", meta["quality"])
        setattr(item, "is_hindi_dubbed", meta["is_hindi_dubbed"])
        out.append(item)

    return out


def parse_detail(html: str, detail_url: str, base_url: str = MOVIESDRIVE_MIRRORS[0]) -> dict:
    """Extract IMDb ID, TMDb ID (if present), synopsis, poster, and print quality from a detail page."""
    soup = BeautifulSoup(html or "", "lxml")
    info: dict = {
        "detail_url": detail_url,
        "imdb": None,
        "tmdb_id": None,
        "synopsis": "",
        "poster_url": None,
        "quality": None,
    }

    m_imdb = _IMDB_RE.search(html or "")
    if m_imdb:
        info["imdb"] = m_imdb.group(1)

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

    title_tag = soup.title.get_text(" ", strip=True) if soup.title else ""
    q = extract_print_quality(title_tag)
    if q:
        info["quality"] = q

    return info


def iter_catalog(
    *,
    max_pages: int = 3,
    mirrors: Sequence[str] = MOVIESDRIVE_MIRRORS,
    delay: float = 0.4,
    session: Optional[requests.Session] = None,
) -> Iterator[MediaItem]:
    """Yield unique MediaItems from configured MoviesDrive mirrors."""
    owns_session = session is None
    sess = session if session is not None else requests.Session()
    headers = {"User-Agent": DEFAULT_UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    seen: set[str] = set()

    try:
        req_count = 0
        for raw_mirror in mirrors:
            base = raw_mirror.rstrip("/")
            mirror_found = 0
            for page in range(1, max(1, max_pages) + 1):
                url = f"{base}/" if page == 1 else f"{base}/page/{page}/"
                if req_count > 0 and delay > 0:
                    time.sleep(delay)
                req_count += 1
                try:
                    r = sess.get(url, headers=headers, timeout=15, allow_redirects=True)
                    if r.status_code != 200 or "just a moment" in (r.text or "").lower()[:600]:
                        logger.warning("MoviesDrive page skipped (status=%s): %s", r.status_code, url)
                        break
                    items = parse_listing(r.text, base_url=base)
                    if not items:
                        break
                    for it in items:
                        if it.source_id not in seen:
                            seen.add(it.source_id)
                            mirror_found += 1
                            yield it
                except Exception as exc:
                    logger.warning("MoviesDrive fetch error on %s: %s", url, exc)
                    break
            logger.info("MoviesDrive mirror %s yielded %d unique items", base, mirror_found)
    finally:
        if owns_session:
            sess.close()
