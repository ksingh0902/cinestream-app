-- app/db/schema.sql
-- Additive migration for cinemymovies dual-source streaming layer.
-- Does not alter existing rows or delete columns.

-- 1. Base table creation (for fresh databases)
CREATE TABLE IF NOT EXISTS movies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL DEFAULT 'yomovies',
  source_id TEXT,
  title TEXT NOT NULL,
  year INTEGER,
  language TEXT,
  language_code TEXT,
  poster_url TEXT,
  duration_s INTEGER,
  rating REAL,
  genres TEXT,
  synopsis TEXT,
  tmdb_id INTEGER,
  is_series INTEGER DEFAULT 0,
  detail_url TEXT,
  watch_url TEXT,
  player_url TEXT,
  player_kind TEXT DEFAULT 'iframe',
  servers_json TEXT,
  resolved_at INTEGER,
  updated_at INTEGER,
  UNIQUE(source, source_id)
);

-- 2. Additive columns for existing databases (applied via migrate.py with column checks):
-- ALTER TABLE movies ADD COLUMN source        TEXT DEFAULT 'yomovies';
-- ALTER TABLE movies ADD COLUMN source_id     TEXT;
-- ALTER TABLE movies ADD COLUMN poster_url    TEXT;
-- ALTER TABLE movies ADD COLUMN rating        REAL;
-- ALTER TABLE movies ADD COLUMN detail_url    TEXT;
-- ALTER TABLE movies ADD COLUMN player_url    TEXT;
-- ALTER TABLE movies ADD COLUMN language      TEXT;
-- ALTER TABLE movies ADD COLUMN language_code TEXT;
-- ALTER TABLE movies ADD COLUMN tmdb_id       INTEGER;
-- ALTER TABLE movies ADD COLUMN watch_url     TEXT;
-- ALTER TABLE movies ADD COLUMN player_kind   TEXT DEFAULT 'iframe';
-- ALTER TABLE movies ADD COLUMN servers_json  TEXT;
-- ALTER TABLE movies ADD COLUMN resolved_at   INTEGER;

-- 3. Indexes
CREATE INDEX IF NOT EXISTS idx_movies_source ON movies(source, is_series);
CREATE INDEX IF NOT EXISTS idx_movies_title  ON movies(title);
