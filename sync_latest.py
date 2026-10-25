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

from app.sync import run_full_sync

def main():
    parser = argparse.ArgumentParser(description="Sync latest movies from Yomovies and Ask4movie")
    args = parser.parse_args()
    run_full_sync()

if __name__ == "__main__":
    main()
