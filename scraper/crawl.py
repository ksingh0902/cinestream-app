"""Resumable full-catalogue crawl."""
from __future__ import annotations

import time
from typing import Iterator

from config import CRAWL_DELAY, SITE_MIRRORS
from .extract import parse_listing, parse_pagination, parse_detail, is_erotic_content
from .http import HttpClient
from .store import connect, upsert, set_meta

SEEDS = [
    "/series/", "/genre/top-rated/",
    "/genre/bollywood/", "/genre/hollywood/", "/genre/hollywood-dubbed/",
    "/genre/south-special/", "/genre/dual-audio/", "/genre/web-series/",
    "/genre/tv-shows/", "/genre/action/",
    "/genre/comedy/", "/genre/drama/", "/genre/thriller/", "/genre/horror/",
    "/genre/animation/", "/genre/romantic/", "/genre/crime/",
    "/genre/science-fiction/", "/genre/fantasy/", "/genre/mystery/",
    "/genre/adventure/", "/genre/family/", "/genre/history/",
    "/genre/biography/", "/genre/music/", "/genre/sport/", "/genre/war/",
    "/genre/unofficial-dubbed/", "/genre/bengali/",
    "/genre/tamil/", "/genre/telugu/", "/genre/malayalam/", "/genre/kannada/",
    "/genre/marathi/", "/genre/gujarati/", "/genre/punjabi/",
] + [f"/release-year/{y}/" for y in range(2026, 1949, -1)]


def is_allowed_title(card: dict) -> bool:
    """Strictly reject erotic/softcore webseries and channels (Ullu, AltBalaji, etc.)

    while allowing mainstream 18+ titles (Game of Thrones, Person of Interest, etc.).
    """
    return not is_erotic_content(card)


def pick_base(http: HttpClient) -> str:
    """R3/R6: first mirror that answers wins."""
    for base in SITE_MIRRORS:
        try:
            http.get(base + "/", force=True)
            print(f"[site] using {base}")
            return base
        except Exception:
            print(f"[site] {base} unreachable")
    raise SystemExit("no reachable mirror")


def _pages(http: HttpClient, base: str, path: str, max_pages: int) -> Iterator[dict]:
    page = 1
    while page <= max_pages:
        url = base + path if page == 1 else f"{base}{path}page/{page}/"
        try:
            html = http.get(url)
        except Exception:
            return
        cards = parse_listing(html, base)
        if not cards:
            return
        yield from cards
        nxt = parse_pagination(html, base)
        if not nxt:
            return
        page += 1


def crawl(db: str = "yomovies.db", *, delay: float = CRAWL_DELAY,
          max_detail: int | None = None, max_pages: int = 400):
    http = HttpClient(delay=delay)
    base = pick_base(http)
    con = connect(db)

    targets, seen = [], set()
    for seed in SEEDS:
        for card in _pages(http, base, seed, max_pages):
            if not is_allowed_title(card):
                continue
            if card["url"] in seen:
                continue
            seen.add(card["url"]); targets.append(card["url"])
            upsert(con, {**card, "updated_at": int(time.time())})
            if max_detail and len(targets) >= max_detail:
                break
        print(f"[list] {seed} -> {len(targets)}", flush=True)
        if max_detail and len(targets) >= max_detail:
            break
    set_meta(con, "site_base", base)

    done = 0
    for url in targets:
        if max_detail and done >= max_detail:
            break
        existing = con.execute(
            "SELECT synopsis, embeds, downloads FROM movies WHERE url=?", (url,)
        ).fetchone()
        if existing and any(
            value and str(value).strip() not in ("", "[]", "null")
            for value in existing
        ):
            continue
        try:
            html = http.get(url)
        except Exception:
            continue
        info = parse_detail(html, url)
        info["updated_at"] = int(time.time())
        upsert(con, info)
        done += 1
        if done % 25 == 0:
            print(f"[detail] {done}/{len(targets)} {info['title']}", flush=True)

    set_meta(con, "last_run", str(int(time.time())))
    http.close(); con.close()
    return done
