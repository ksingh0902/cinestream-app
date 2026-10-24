#!/usr/bin/env python3
"""
Sync Latest Movies from Yomovies to CineMyMovies
Run this anytime to fetch newly released movies and series from Yomovies into yomovies.db.
Usage:
    python sync_latest.py
    python sync_latest.py --push  (auto-commits and pushes to GitHub to redeploy Render)
"""

import sys
import os
import time
import argparse
import subprocess
from urllib.parse import urljoin
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

from scraper.http import HttpClient
from scraper.extract import parse_listing, parse_detail
from scraper.store import connect, upsert

BASE_URL = "https://yomovies.wine"

SYNC_PAGES = [
    # Homepage & featured
    ("/", 1),
    # 2026 releases (first 3 pages)
    ("/release-year/2026/", 3),
    # Latest Bollywood & Punjabi & Series (first 2 pages each)
    ("/genre/bollywood/", 2),
    ("/genre/punjabi/", 2),
    ("/genre/web-series/", 2),
    ("/movies/", 2),
]


def sync(auto_push: bool = False):
    print("=" * 60)
    print("🚀 CineMyMovies Catalogue Sync")
    print(f"Connecting to {BASE_URL}...")
    print("=" * 60)

    http = HttpClient(delay=0.1, cache_dir=".cache")
    con = connect("yomovies.db")

    urls_to_check = []
    seen = set()

    for path, max_p in SYNC_PAGES:
        for p in range(1, max_p + 1):
            url = f"{BASE_URL}{path}" if p == 1 else f"{BASE_URL}{path}page/{p}/"
            try:
                html = http.get(url, force=True)
                cards = parse_listing(html, BASE_URL)
                new_in_page = 0
                for c in cards:
                    u = c.get("url")
                    if u and u not in seen:
                        seen.add(u)
                        urls_to_check.append(u)
                        new_in_page += 1
                print(f"[{path} p.{p}] Found {len(cards)} items ({new_in_page} new)")
            except Exception as e:
                print(f"Error fetching {url}: {e}")

    print(f"\nTotal unique catalogue URLs checked: {len(urls_to_check)}")

    added = 0
    updated = 0
    cur = con.cursor()

    for idx, u in enumerate(urls_to_check):
        try:
            cur.execute("SELECT id, title, embeds FROM movies WHERE url=?", (u,))
            row = cur.fetchone()
            if row and row["embeds"] and row["embeds"] != "[]":
                continue

            html = http.get(u, force=False)
            info = parse_detail(html, u)
            if not info or not info.get("title"):
                continue

            if "/genre/punjabi/" in u or "punjabi" in str(info.get("title", "")).lower():
                g = info.get("genres") or []
                if isinstance(g, list) and not any("punjabi" in str(x).lower() for x in g):
                    g.append("Punjabi")
                    info["genres"] = g

            info["updated_at"] = int(time.time())
            upsert(con, info)

            embs = info.get("embeds", [])
            print(f"[{idx+1}/{len(urls_to_check)}] {info['title']} ({info.get('year')}) -> {len(embs)} embeds")
            if row:
                updated += 1
            else:
                added += 1

        except Exception as e:
            print(f"Error ingesting {u}: {e}")

    con.close()
    http.close()

    print("=" * 60)
    print(f"✅ Sync Finished! Added: {added} new titles, Updated: {updated} titles.")
    print("=" * 60)

    if auto_push and (added > 0 or updated > 0):
        print("\nPushing updated database to GitHub for auto-deploy on Render...")
        try:
            subprocess.run(["git", "add", "yomovies.db"], check=True)
            subprocess.run(["git", "commit", "-m", f"Sync catalogue: added {added}, updated {updated} titles"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            print("🎉 Successfully pushed to main! Render is now deploying the fresh catalogue.")
        except Exception as e:
            print(f"Git push failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync latest movies from Yomovies")
    parser.add_argument("--push", action="store_true", help="Auto-commit and push yomovies.db to GitHub")
    args = parser.parse_args()
    sync(auto_push=args.push)
