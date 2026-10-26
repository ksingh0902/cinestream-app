"""Resumable full YoMovies import for movies, series, and Hindi-dubbed titles."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from config import CRAWL_DELAY, DB_PATH
from scraper.crawl import crawl


def mirror_database(source: Path, destination: Path) -> None:
    if source.resolve() == destination.resolve():
        return
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--mirror-db", default="yomovies.db")
    parser.add_argument("--target", type=int, default=25_000)
    parser.add_argument("--max-pages", type=int, default=400)
    parser.add_argument("--delay", type=float, default=CRAWL_DELAY)
    args = parser.parse_args()

    imported = crawl(
        args.db,
        delay=args.delay,
        max_detail=args.target,
        max_pages=args.max_pages,
    )
    if args.mirror_db:
        mirror_database(Path(args.db), Path(args.mirror_db))
    print(f"YoMovies bulk import complete: {imported} detail pages refreshed")


if __name__ == "__main__":
    main()
