from __future__ import annotations

import sqlite3
from pathlib import Path


COLUMNS_TO_ADD = [
    ("source", "TEXT DEFAULT 'yomovies'"),
    ("source_id", "TEXT"),
    ("poster_url", "TEXT"),
    ("rating", "REAL"),
    ("detail_url", "TEXT"),
    ("player_url", "TEXT"),
    ("language", "TEXT"),
    ("language_code", "TEXT"),
    ("tmdb_id", "INTEGER"),
    ("watch_url", "TEXT"),
    ("player_kind", "TEXT DEFAULT 'iframe'"),
    ("servers_json", "TEXT"),
    ("resolved_at", "INTEGER"),
    ("first_added_at", "INTEGER"),
    ("last_checked_at", "INTEGER"),
    ("last_updated_at", "INTEGER"),
    ("last_quality_upgrade_at", "INTEGER"),
    ("best_quality", "TEXT"),
    ("latest_quality_transition", "TEXT"),
]


def migrate_database(db_path: str) -> None:
    """Safely apply additive migrations with column existence checks."""
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        
        # Check if table exists
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movies'")
        if not cur.fetchone():
            schema_file = Path(__file__).parent / "schema.sql"
            if schema_file.exists():
                conn.executescript(schema_file.read_text(encoding="utf-8"))
            conn.commit()
            return

        # Table exists: inspect existing columns
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(movies)").fetchall()}

        for col_name, col_type in COLUMNS_TO_ADD:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE movies ADD COLUMN {col_name} {col_type}")

        # Backfill source A columns for legacy rows if needed
        conn.execute("""
            UPDATE movies SET
                source = 'yomovies'
            WHERE source IS NULL OR source = ''
        """)
        conn.execute("""
            UPDATE movies SET
                source_id = COALESCE(slug, CAST(id AS TEXT))
            WHERE source_id IS NULL OR source_id = ''
        """)
        conn.execute("""
            UPDATE movies SET
                poster_url = poster
            WHERE (poster_url IS NULL OR poster_url = '') AND poster IS NOT NULL
        """)
        conn.execute("""
            UPDATE movies SET
                detail_url = url
            WHERE (detail_url IS NULL OR detail_url = '') AND url IS NOT NULL
        """)
        conn.execute("""
            UPDATE movies SET
                player_kind = 'hls'
            WHERE source = 'yomovies' AND (player_kind IS NULL OR player_kind = '' OR player_kind = 'iframe')
        """)

        # Backfill discovery and recency timestamps for existing catalogue records
        conn.execute("""
            UPDATE movies SET
                first_added_at = COALESCE(updated_at, 1792800000)
            WHERE first_added_at IS NULL
        """)
        conn.execute("""
            UPDATE movies SET
                last_checked_at = COALESCE(updated_at, 1792800000)
            WHERE last_checked_at IS NULL
        """)
        conn.execute("""
            UPDATE movies SET
                last_updated_at = COALESCE(updated_at, 1792800000)
            WHERE last_updated_at IS NULL
        """)
        conn.execute("""
            UPDATE movies SET
                best_quality = quality
            WHERE best_quality IS NULL AND quality IS NOT NULL
        """)

        # Quality history table for tracking verified quality improvements
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quality_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                movie_id INTEGER NOT NULL,
                old_quality TEXT,
                new_quality TEXT NOT NULL,
                transition_badge TEXT NOT NULL,
                upgraded_at INTEGER NOT NULL,
                evidence TEXT,
                FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE
            )
        """)

        # Indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movies_source ON movies(source, is_series)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movies_title ON movies(title)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_movies_source_source_id ON movies(source, source_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movies_first_added ON movies(first_added_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movies_last_upgraded ON movies(last_quality_upgrade_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quality_history_upgraded ON quality_history(upgraded_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quality_history_movie ON quality_history(movie_id)")
        
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    import os
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else os.getenv("DB_PATH", "cinemymovies.sqlite3")
    migrate_database(target)
    print(f"[migration] Successfully migrated {target}")
