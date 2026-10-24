#!/usr/bin/env python3
"""Fast catalogue populator: crawls listing pages until 1000+ movies are stored."""
import time
import sys
from scraper.http import HttpClient
from scraper.store import connect, upsert, set_meta
from scraper.extract import parse_listing, parse_pagination
from scraper.crawl import SEEDS, pick_base

TARGET_COUNT = 1050

def run():
    print(f"Starting catalogue crawl targeting {TARGET_COUNT}+ titles...", flush=True)
    con = connect("yomovies.db")
    http = HttpClient(delay=0.1)
    base = pick_base(http)

    current_total = con.execute("SELECT COUNT(*) FROM movies WHERE title IS NOT NULL AND title != ''").fetchone()[0]
    print(f"Existing titles in DB: {current_total}", flush=True)

    seen = set(r[0] for r in con.execute("SELECT url FROM movies WHERE url IS NOT NULL").fetchall())

    for seed in SEEDS:
        if current_total >= TARGET_COUNT:
            break

        page = 1
        max_pages_per_seed = 10
        while page <= max_pages_per_seed and current_total < TARGET_COUNT:
            url = base + seed if page == 1 else f"{base}{seed}page/{page}/"
            try:
                html = http.get(url)
            except Exception as e:
                print(f"Error fetching {url}: {e}", flush=True)
                break

            cards = parse_listing(html, base)
            if not cards:
                break

            new_in_page = 0
            for card in cards:
                u = card.get("url")
                if not u or u in seen:
                    continue
                seen.add(u)
                card["updated_at"] = int(time.time())
                upsert(con, card)
                new_in_page += 1
                current_total += 1
                if current_total >= TARGET_COUNT:
                    break

            print(f"[page] {seed} p{page} -> +{new_in_page} (Total in DB: {current_total})", flush=True)
            nxt = parse_pagination(html, base)
            if not nxt:
                break
            page += 1

    set_meta(con, "site_base", base)
    set_meta(con, "last_catalogue_sync", str(int(time.time())))
    http.close()
    con.close()
    print(f"SUCCESS: Crawled and populated {current_total} movies into yomovies.db!", flush=True)

if __name__ == "__main__":
    run()
