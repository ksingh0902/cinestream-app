#!/usr/bin/env python3
"""
Sync Latest Movies from Yomovies & Ask4movie to CineMyMovies.
Updates both cinemymovies.sqlite3 and yomovies.db with newly added movies.
Usage:
    python sync_latest.py
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

import time
from app.sync import run_full_sync, sync_yomovies, sync_ask4movie
from app.adapters.movies7.sync import sync_movies7

def main():
    parser = argparse.ArgumentParser(description="Sync latest movies from Yomovies and other sources")
    parser.add_argument("--source", choices=["all", "yomovies", "prmovies", "ask4movie", "movies7"], default="all",
                        help="Which source to sync (default: all)")
    args = parser.parse_args()

    if args.source == "all":
        run_full_sync()
    elif args.source == "yomovies":
        base_time = int(time.time())
        res = sync_yomovies(base_time)
        try:
            from app.api.routes_catalog import invalidate_catalog_cache, prewarm_catalog_cache
            invalidate_catalog_cache()
            prewarm_catalog_cache()
        except Exception as exc:
            print(f"[SYNC] Note: catalog cache invalidation skipped: {exc}", flush=True)
        print(f"\n[YOMOVIES SYNC COMPLETE] Added: {res.get('added', 0)}, Refreshed: {res.get('updated', 0)}, Scanned: {res.get('total', 0)}")
    elif args.source == "prmovies":
        base_time = int(time.time())
        res = sync_yomovies(base_time, base_urls=["https://prmovies.ventures"])
        try:
            from app.api.routes_catalog import invalidate_catalog_cache, prewarm_catalog_cache
            invalidate_catalog_cache()
            prewarm_catalog_cache()
        except Exception as exc:
            print(f"[SYNC] Note: catalog cache invalidation skipped: {exc}", flush=True)
        print(f"\n[PRMOVIES SYNC COMPLETE] Added: {res.get('added', 0)}, Refreshed: {res.get('updated', 0)}, Scanned: {res.get('total', 0)}")
    elif args.source == "ask4movie":
        base_time = int(time.time())
        res = sync_ask4movie(base_time)
        print(f"\n[ASK4MOVIE SYNC COMPLETE] Added: {res.get('added', 0)}, Refreshed: {res.get('updated', 0)}")
    elif args.source == "movies7":
        res = sync_movies7(pages_per_category=5)
        print(f"\n[MOVIES7 SYNC COMPLETE] Total processed: {res.get('total', 0)}")

if __name__ == "__main__":
    main()
