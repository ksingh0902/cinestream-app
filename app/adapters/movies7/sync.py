from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import time
from typing import Iterator, List

from ..base import MediaItem
from . import catalog, resolver
from .config import CFG

logger = logging.getLogger("movies7.sync")


def get_target_db_paths() -> List[str]:
    paths = []
    if os.path.exists("cinemymovies.sqlite3"):
        paths.append("cinemymovies.sqlite3")
    if os.path.exists("yomovies.db"):
        paths.append("yomovies.db")
    if not paths:
        paths.append("cinemymovies.sqlite3")
    return paths


def slugify(text: str) -> str:
    s = (text or "").lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s or "title"


def upsert_item(conn: sqlite3.Connection, item: MediaItem) -> None:
    # Build default stream servers
    stream_info = resolver.resolve(item.detail_url or "", tmdb_id=item.tmdb_id, is_series=item.is_series)
    servers_json = json.dumps(stream_info.servers)
    now = int(time.time())

    genres_val = item.genres or "[]"
    if isinstance(genres_val, list):
        genres_val = json.dumps(genres_val)

    slug = f"7-{slugify(item.title)}-{item.tmdb_id or item.source_id}"

    data = {
        "source": item.source,
        "source_id": item.source_id,
        "slug": slug,
        "title": item.title,
        "year": str(item.year) if item.year else None,
        "language": item.language,
        "language_code": item.language_code,
        "poster_url": item.poster_url,
        "poster": item.poster_url,
        "duration_s": item.duration_s,
        "rating": item.rating,
        "genres": genres_val,
        "synopsis": item.synopsis,
        "tmdb_id": item.tmdb_id,
        "is_series": 1 if item.is_series else 0,
        "detail_url": item.detail_url,
        "url": item.detail_url,
        "player_kind": item.player_kind or "iframe",
        "player_url": stream_info.url,
        "servers_json": servers_json,
        "resolved_at": now,
        "updated_at": now,
        "is_hindi_dubbed": 1 if item.language_code == "hi" else 0,
    }

    conn.execute(
        """
        INSERT INTO movies (source, source_id, slug, title, year, language, language_code,
                            poster_url, poster, duration_s, rating, genres, synopsis, tmdb_id,
                            is_series, detail_url, url, player_kind, player_url, servers_json,
                            resolved_at, updated_at, is_hindi_dubbed)
        VALUES (:source, :source_id, :slug, :title, :year, :language, :language_code,
                :poster_url, :poster, :duration_s, :rating, :genres, :synopsis, :tmdb_id,
                :is_series, :detail_url, :url, :player_kind, :player_url, :servers_json,
                :resolved_at, :updated_at, :is_hindi_dubbed)
        ON CONFLICT(source, source_id) DO UPDATE SET
            title=excluded.title,
            year=excluded.year,
            language=excluded.language,
            language_code=excluded.language_code,
            poster_url=excluded.poster_url,
            poster=excluded.poster,
            rating=excluded.rating,
            genres=excluded.genres,
            synopsis=excluded.synopsis,
            tmdb_id=excluded.tmdb_id,
            is_series=excluded.is_series,
            detail_url=excluded.detail_url,
            url=excluded.url,
            player_url=excluded.player_url,
            servers_json=excluded.servers_json,
            resolved_at=excluded.resolved_at,
            updated_at=excluded.updated_at
        """,
        data,
    )


def sync_movies7(pages_per_category: int = 5) -> dict:
    """Sync movies and web series from Movies7 into databases."""
    logger.info("Starting Movies7 sync (pages_per_category=%d)...", pages_per_category)
    db_paths = get_target_db_paths()

    connections = [sqlite3.connect(p, timeout=30) for p in db_paths]
    for c in connections:
        c.execute("PRAGMA journal_mode=WAL")

    count_movies = 0
    count_series = 0

    try:
        items = list(catalog.iter_catalog(max_pages=pages_per_category))
        logger.info("Fetched %d unique items from Movies7 endpoints", len(items))

        for it in items:
            for c in connections:
                upsert_item(c, it)
            if it.is_series:
                count_series += 1
            else:
                count_movies += 1

        for c in connections:
            c.commit()
    finally:
        for c in connections:
            c.close()

    total = count_movies + count_series
    logger.info("Movies7 sync finished: %d total (%d movies, %d series)", total, count_movies, count_series)
    return {
        "status": "success",
        "total": total,
        "movies": count_movies,
        "series": count_series,
        "db_paths": db_paths,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Movies7 catalog")
    parser.add_argument("--pages", type=int, default=5, help="Pages per category (default 5)")
    args = parser.parse_args()
    res = sync_movies7(pages_per_category=args.pages)
    print("Sync result:", res)
