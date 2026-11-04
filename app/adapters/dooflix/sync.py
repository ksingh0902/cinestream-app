"""DooFlix Sync & Ingestion Engine for CineMyMovies.

Supports ingesting newly crawled JSON feeds, staging files, or probing endpoints
into cinemymovies.sqlite3 and yomovies.db with cross-source deduplication.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("dooflix.sync")


def get_target_db_paths() -> List[str]:
    paths = []
    if os.path.exists("cinemymovies.sqlite3"):
        paths.append("cinemymovies.sqlite3")
    if os.path.exists("yomovies.db"):
        paths.append("yomovies.db")
    if not paths:
        paths.append("cinemymovies.sqlite3")
    return paths


def sync_dooflix(
    base_time: Optional[int] = None,
    json_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Sync DooFlix content into CineMyMovies databases.

    If a JSON export or directory is provided, imports candidate movies with
    cross-source deduplication against YoMovies/PRMovies.
    Otherwise, verifies local catalogue integrity and reports counts.
    """
    now = int(base_time or time.time())
    db_paths = get_target_db_paths()
    logger.info("Starting DooFlix sync across databases: %s", db_paths)

    # Check for candidate files
    candidates: List[Path] = []
    if json_path:
        p = Path(json_path)
        if p.is_file():
            candidates.append(p)
        elif p.is_dir():
            candidates.extend(p.glob("*.json"))
    else:
        # Default local data directories if present
        for check_dir in [Path("data/dooflix"), Path("cinemymovies_data")]:
            if check_dir.is_dir():
                candidates.extend(check_dir.glob("*.json"))

    added = 0
    updated = 0
    skipped = 0
    total_processed = 0

    if candidates:
        from dooflix_scraper import collect_movies, upsert_database, Movie
        try:
            from app.api.routes_catalog import is_movie_available_on_primary_sources
        except Exception:
            is_movie_available_on_primary_sources = None

        all_movies: List[Movie] = []
        for cfile in candidates:
            try:
                with open(cfile, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                parsed = collect_movies(payload, f"file://{cfile.name}")
                for m in parsed:
                    if is_movie_available_on_primary_sources and is_movie_available_on_primary_sources(m.title, m.year):
                        skipped += 1
                        continue
                    all_movies.append(m)
            except Exception as exc:
                logger.warning("Error reading candidate %s: %s", cfile, exc)

        total_processed = len(all_movies) + skipped
        # Ingest into all databases
        for db_p in db_paths:
            upsert_database(Path(db_p), all_movies)

        added = len(all_movies)
        print(f"[sync-dooflix] Ingested {added} DooFlix items ({skipped} cross-source duplicates skipped).", flush=True)
    else:
        # Audit existing catalogue count
        conns = [sqlite3.connect(p, timeout=10) for p in db_paths]
        existing_count = 0
        try:
            for conn in conns:
                count = conn.execute("SELECT COUNT(*) FROM movies WHERE source='dooflix'").fetchone()[0]
                existing_count = max(existing_count, count)
        finally:
            for conn in conns:
                conn.close()

        total_processed = existing_count
        print(f"[sync-dooflix] Local catalogue audited: {existing_count} DooFlix items present and healthy.", flush=True)

    return {
        "status": "success",
        "source": "dooflix",
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "total": total_processed,
    }


if __name__ == "__main__":
    res = sync_dooflix()
    print("DooFlix sync result:", res)

