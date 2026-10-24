#!/usr/bin/env python3
import argparse
from scraper import crawl

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="yomovies.db")
    p.add_argument("--delay", type=float, default=0.6)
    p.add_argument("--max-detail", type=int, default=None)
    p.add_argument("--max-pages", type=int, default=400)
    a = p.parse_args()
    print("processed:", crawl(a.db, delay=a.delay,
                              max_detail=a.max_detail, max_pages=a.max_pages))
