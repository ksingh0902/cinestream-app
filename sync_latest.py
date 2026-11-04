#!/usr/bin/env python3
"""
Sync Latest Movies & Web Series across YoMovies, PRMovies, Ask4Movies, DuoFlix, and Movies7.
Updates both cinemymovies.sqlite3 and yomovies.db with newly added titles and de-duplication.

Usage:
    python sync_latest.py                     # Sync all 5 sources
    python sync_latest.py --source yomovies   # Sync Yomovies only
    python sync_latest.py --source prmovies   # Sync PRMovies only
    python sync_latest.py --source ask4movie  # Sync Ask4movies only
    python sync_latest.py --source movies7    # Sync Movies7 only
    python sync_latest.py --source duoflix    # Sync/Audit DuoFlix only
    python sync_latest.py --report-only       # Print current catalogue counts without crawling
"""

import sys
import os
import argparse
import sqlite3
import time

sys.path.insert(0, os.path.abspath('.'))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')
    except Exception:
        pass

from app.sync import run_full_sync, sync_yomovies, sync_ask4movie
from app.adapters.movies7.sync import sync_movies7
from app.adapters.dooflix.sync import sync_dooflix


def get_catalogue_summary() -> dict:
    """Read current catalogue counts per source from yomovies.db / cinemymovies.sqlite3."""
    db = "yomovies.db" if os.path.exists("yomovies.db") else "cinemymovies.sqlite3"
    counts = {}
    total = 0
    if os.path.exists(db):
        conn = sqlite3.connect(db)
        try:
            rows = conn.execute("SELECT source, COUNT(*) FROM movies GROUP BY source").fetchall()
            counts = {r[0]: r[1] for r in rows}
            total = sum(counts.values())
        finally:
            conn.close()
    return {"counts": counts, "total": total, "db": db}


def print_catalogue_report():
    summary = get_catalogue_summary()
    print("=" * 65)
    print(" CineMyMovies Catalogue Status Report")
    print(f" Database: {summary['db']} | Total Titles: {summary['total']}")
    print("=" * 65)
    print(f" {'Source':<15} | {'Count':<10}")
    print("-" * 30)
    for src, cnt in sorted(summary["counts"].items()):
        print(f" {src:<15} | {cnt:<10}")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="Sync latest movies from Yomovies, PRMovies, Ask4Movies, DuoFlix, Movies7")
    parser.add_argument(
        "--source",
        choices=["all", "yomovies", "prmovies", "ask4movie", "movies7", "duoflix"],
        default="all",
        help="Which source to sync (default: all)"
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only display current database statistics without crawling"
    )
    args = parser.parse_args()

    if args.report_only:
        print_catalogue_report()
        return

    before = get_catalogue_summary()

    if args.source == "all":
        res = run_full_sync()
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
        print(f"\n[ASK4MOVIE SYNC COMPLETE] Added: {res.get('added', 0)}, Refreshed: {res.get('updated', 0)}, Scanned: {res.get('total', 0)}")
    elif args.source == "movies7":
        res = sync_movies7(pages_per_category=5)
        print(f"\n[MOVIES7 SYNC COMPLETE] Added: {res.get('added', 0)}, Refreshed: {res.get('updated', 0)}, Duplicates Skipped: {res.get('skipped', 0)}, Scanned: {res.get('total', 0)}")
    elif args.source == "duoflix":
        base_time = int(time.time())
        res = sync_dooflix(base_time)
        print(f"\n[DUOFLIX SYNC COMPLETE] Added: {res.get('added', 0)}, Refreshed: {res.get('updated', 0)}, Duplicates Skipped: {res.get('skipped', 0)}, Total: {res.get('total', 0)}")

    after = get_catalogue_summary()
    print("\n" + "=" * 65)
    print(f" CRAWLER FINISHED | Total Catalogue: {after['total']} (+{after['total'] - before['total']} new)")
    print("=" * 65)


if __name__ == "__main__":
    main()
