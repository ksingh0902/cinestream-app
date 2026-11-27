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
from app.adapters.flixmovie.sync import sync_flixmovie
from app.adapters.moviesdrive.sync import sync_moviesdrive


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
        choices=["all", "yomovies", "prmovies", "moviesdrive", "ask4movie", "movies7", "duoflix", "flixmovie"],
        default="all",
        help="Which source to sync (default: all)"
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only display current database statistics without crawling"
    )
    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="Validate Telegram report formatting & env configuration without running the crawler or touching any DB"
    )
    parser.add_argument(
        "--test-ntfy",
        action="store_true",
        help="Validate or send a sample ntfy push report without running the crawler or touching any DB"
    )
    args = parser.parse_args()

    if args.test_telegram or args.test_ntfy:
        from app.adapters.registry import ADAPTERS
        from app.notifications import (
            NtfyNotifier,
            OverallStatus,
            SourceRunReport,
            SourceStatus,
            SyncRunReport,
            TelegramNotifier,
        )
        now = int(time.time())
        label_map = {
            "yomovies": "YoMovies",
            "moviesdrive": "MoviesDrive",
            "ask4movie": "Ask4Movies",
            "movies7": "Movies7",
            "dooflix": "DuoFlix",
            "flixmovie": "FlixMovie",
        }
        sample_sources = []
        for key in ADAPTERS.keys():
            lbl = label_map.get(key, key.title())
            if key == "yomovies":
                sample_sources.append(SourceRunReport(source=lbl, status=SourceStatus.BLOCKED, http_status=403, blocked_reason="Cloudflare"))
            else:
                sample_sources.append(SourceRunReport(source=lbl, status=SourceStatus.SUCCESS, discovered=72, inserted=3, updated=12, duplicates=4))
        sample_report = SyncRunReport(
            run_id=f"test-{now}",
            started_at=now - 125,
            finished_at=now,
            duration_seconds=125.0,
            overall_status=OverallStatus.SUCCESS_WITH_WARNINGS,
            sources=sample_sources,
            warnings=["YoMovies HTTP 403"],
            catalogue_total=16353,
        )
        if args.test_ntfy:
            notifier = NtfyNotifier.from_env()
            mode_label = "NTFY"
        else:
            notifier = TelegramNotifier.from_env()
            mode_label = "TELEGRAM"
        formatted = notifier.format_sync_report(sample_report)
        ready, reason = notifier.config.is_ready()
        print(f"=== {mode_label} TEST MODE (NO CRAWLER / NO DB WRITES) ===", flush=True)
        print(f"Config ready: {ready} ({reason})", flush=True)
        print("--- Formatted Preview ---", flush=True)
        print(formatted, flush=True)
        print("-------------------------", flush=True)
        if ready:
            send_res = notifier.send_sync_report(sample_report)
            print(f"Send result: sent={send_res.sent} messages={send_res.messages_sent} reason={send_res.reason}", flush=True)
        else:
            print(f"{mode_label} disabled or unconfigured -> dry-run validation only (no message sent).", flush=True)
        return

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
    elif args.source == "moviesdrive":
        base_time = int(time.time())
        res = sync_moviesdrive(base_time, pages_per_mirror=3)
        try:
            from app.api.routes_catalog import invalidate_catalog_cache, prewarm_catalog_cache
            invalidate_catalog_cache()
            prewarm_catalog_cache()
        except Exception as exc:
            print(f"[SYNC] Note: catalog cache invalidation skipped: {exc}", flush=True)
        print(f"\n[MOVIESDRIVE SYNC COMPLETE] Added: {res.get('added', 0)}, Refreshed: {res.get('updated', 0)}, Duplicates Skipped: {res.get('skipped', 0)}, Scanned: {res.get('total', 0)}")
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
    elif args.source == "flixmovie":
        base_time = int(time.time())
        res = sync_flixmovie(base_time, pages_per_category=2)
        try:
            from app.api.routes_catalog import invalidate_catalog_cache, prewarm_catalog_cache
            invalidate_catalog_cache()
            prewarm_catalog_cache()
        except Exception as exc:
            print(f"[SYNC] Note: catalog cache invalidation skipped: {exc}", flush=True)
        print(f"\n[FLIXMOVIE SYNC COMPLETE] Added: {res.get('added', 0)}, Refreshed: {res.get('updated', 0)}, Duplicates Skipped: {res.get('skipped', 0)}, Scanned: {res.get('total', 0)}")

    after = get_catalogue_summary()
    # For single-source runs, emit one best-effort notification when explicitly enabled
    if args.source != "all":
        try:
            from app.notifications import NtfyNotifier, TelegramNotifier, build_sync_run_report, source_report_from_dict
            finished_ts = int(time.time())
            src_rep = source_report_from_dict(args.source, res if isinstance(res, dict) else {}, started_at=base_time if "base_time" in locals() else finished_ts, finished_at=finished_ts)
            run_rep = build_sync_run_report(
                [src_rep],
                started_at=src_rep.started_at or finished_ts,
                finished_at=finished_ts,
                catalogue_total=after.get("total"),
            )
            TelegramNotifier.from_env().send_sync_report(run_rep)
            NtfyNotifier.from_env().send_sync_report(run_rep)
        except Exception:
            pass

    print("\n" + "=" * 65)
    print(f" CRAWLER FINISHED | Total Catalogue: {after['total']} (+{after['total'] - before['total']} new)")
    print("=" * 65)


if __name__ == "__main__":
    main()
