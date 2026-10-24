"""python -m app.adapters.ask4movie.sync [--target N] [--limit N]"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..base import MediaItem
from . import catalog, resolver, fbox_gate
from .config import CFG
from .http import get

DDL = """
CREATE TABLE IF NOT EXISTS movies (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  source_id TEXT NOT NULL,
  title TEXT NOT NULL,
  year INTEGER, language TEXT, language_code TEXT,
  poster_url TEXT, duration_s INTEGER, rating REAL, genres TEXT,
  synopsis TEXT, tmdb_id INTEGER, is_series INTEGER DEFAULT 0,
  detail_url TEXT, watch_url TEXT,
  player_url TEXT, player_kind TEXT DEFAULT 'iframe',
  servers_json TEXT, resolved_at INTEGER, updated_at INTEGER,
  poster TEXT, url TEXT, slug TEXT,
  UNIQUE(source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_movies_source ON movies(source, is_series);
CREATE INDEX IF NOT EXISTS idx_movies_title  ON movies(title);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    target_path = path or CFG.db_path
    conn = sqlite3.connect(target_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    from app.db.migrate import migrate_database
    migrate_database(target_path)
    return conn


def upsert(conn: sqlite3.Connection, item: MediaItem) -> None:
    # Ensure genres is stored as valid JSON array string
    genres_val = item.genres or "[]"
    if isinstance(genres_val, list):
        genres_val = json.dumps(genres_val)
    elif isinstance(genres_val, str) and not genres_val.strip().startswith("["):
        g_list = [g.strip() for g in genres_val.split(",") if g.strip()]
        genres_val = json.dumps(g_list)

    data = {
        **item.__dict__,
        "genres": genres_val,
        "now": int(time.time()),
        "poster": item.poster_url,
        "url": item.detail_url,
        "slug": f"ask4movie-{item.source_id}",
    }
    conn.execute("""
        INSERT INTO movies (source, source_id, slug, title, year, language, language_code,
                            poster_url, duration_s, rating, genres, synopsis, tmdb_id,
                            is_series, detail_url, player_kind, updated_at, poster, url)
        VALUES (:source, :source_id, :slug, :title, :year, :language, :language_code,
                :poster_url, :duration_s, :rating, :genres, :synopsis, :tmdb_id,
                :is_series, :detail_url, :player_kind, :now, :poster, :url)
        ON CONFLICT(source, source_id) DO UPDATE SET
            title=excluded.title, year=excluded.year, language=excluded.language,
            language_code=excluded.language_code, poster_url=excluded.poster_url,
            duration_s=excluded.duration_s, rating=excluded.rating,
            genres=excluded.genres, synopsis=excluded.synopsis,
            tmdb_id=excluded.tmdb_id, is_series=excluded.is_series,
            detail_url=excluded.detail_url, updated_at=excluded.updated_at,
            poster=excluded.poster_url, url=excluded.detail_url
    """, data)


def crawl_catalog_sources(target: int = 2400) -> list[MediaItem]:
    base = "https://fbox.gd"
    fbox_gate.verify(base, "/movie", force=True)

    urls: list[str] = []

    # 1. Movies pages 1 to 55 (up to 1,320 movies)
    for p in range(1, 56):
        urls.append(f"{base}/movie?page={p}")

    # 2. TV series pages 1 to 50 (up to 1,200 series)
    urls.append(f"{base}/tv")
    for p in range(2, 51):
        urls.append(f"{base}/tv?page={p}")

    # 3. Special curated collections
    for seed in ["/trending", "/latest", "/top-imdb", "/top-movies-2026", "/top-tv-shows-2026"]:
        urls.append(f"{base}{seed}")

    print(f"[catalog] Generated {len(urls)} listing pages to crawl...", flush=True)

    seen: set[str] = set()
    items: list[MediaItem] = []

    def fetch_page(u: str) -> list[MediaItem]:
        for _ in range(2):
            try:
                r = get(u)
                if "<title>Quick check</title>" in r.text or "bf-card" not in r.text:
                    fbox_gate.verify(base, u.replace(base, ""), force=True)
                    r = get(u)
                return catalog.parse_listing(r.text)
            except Exception:
                time.sleep(0.4)
        return []

    t0 = time.time()
    pool = ThreadPoolExecutor(max_workers=8)
    futures = {pool.submit(fetch_page, u): u for u in urls}
    done = 0
    try:
        for fut in as_completed(futures):
            parsed = fut.result()
            done += 1
            for it in parsed:
                if it.source_id not in seen:
                    seen.add(it.source_id)
                    items.append(it)
            if done % 10 == 0 or done == len(urls):
                print(f"[catalog] Scraped {done}/{len(urls)} pages -> {len(items)} unique titles ({time.time()-t0:.1f}s)", flush=True)
            if target and len(items) >= target:
                print(f"[catalog] Target of {target} reached ({len(items)} titles). Wrapping up...", flush=True)
                break
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    # 4. Also include featured ask4movietv.cyou titles
    try:
        r_a4m = get("https://ask4movietv.cyou/movies/")
        for it in catalog.parse_listing(r_a4m.text):
            if it.source_id not in seen:
                seen.add(it.source_id)
                items.append(it)
    except Exception:
        pass

    print(f"[catalog] Crawl complete: {len(items)} unique titles in {time.time()-t0:.1f}s", flush=True)
    return items


def sync_database(db_file: str, items: list[MediaItem]) -> None:
    conn = connect(db_file)
    print(f"[sync] Upserting {len(items)} ask4movie titles into {db_file}...", flush=True)
    for it in items:
        upsert(conn, it)
    conn.commit()

    conn.execute("UPDATE movies SET watch_url=NULL WHERE source='ask4movie'")
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM movies WHERE source='ask4movie'").fetchone()[0]
    movies = conn.execute("SELECT COUNT(*) FROM movies WHERE source='ask4movie' AND is_series=0").fetchone()[0]
    series = conn.execute("SELECT COUNT(*) FROM movies WHERE source='ask4movie' AND is_series=1").fetchone()[0]
    conn.close()
    print(f"[sync] {db_file} populated: {total} total ask4movie titles ({movies} movies, {series} series)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=2400)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-resolve", action="store_true")
    args = ap.parse_args()

    target = args.limit or args.target
    items = crawl_catalog_sources(target=target)

    # Sync to both cinemymovies.sqlite3 and yomovies.db if they exist
    db_paths = set()
    if os.path.exists("cinemymovies.sqlite3"):
        db_paths.add("cinemymovies.sqlite3")
    if os.path.exists("yomovies.db"):
        db_paths.add("yomovies.db")
    if not db_paths:
        db_paths.add(CFG.db_path)

    for db_path in db_paths:
        sync_database(db_path, items)

    print("[sync] SUCCESS: All databases updated!")


if __name__ == "__main__":
    main()
