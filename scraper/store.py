"""SQLite persistence. Only stable facts are stored (R1)."""
from __future__ import annotations

import json
import sqlite3
from typing import Dict, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS movies (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE, url TEXT UNIQUE,
  title TEXT, year TEXT, duration TEXT, duration_s INTEGER,
  quality TEXT, imdb TEXT,
  genres TEXT, actors TEXT, director TEXT, country TEXT,
  poster TEXT, synopsis TEXT, is_series INTEGER DEFAULT 0,
  embeds TEXT, downloads TEXT, updated_at INTEGER
);
CREATE INDEX IF NOT EXISTS ix_year   ON movies(year);
CREATE INDEX IF NOT EXISTS ix_series ON movies(is_series);
CREATE INDEX IF NOT EXISTS ix_upd    ON movies(updated_at);
CREATE INDEX IF NOT EXISTS ix_title  ON movies(title COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def connect(path: str = "yomovies.db") -> sqlite3.Connection:
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA); con.commit()
    return con


def upsert(con, m: Dict) -> None:
    columns = {item[1] for item in con.execute("PRAGMA table_info(movies)")}
    slug = (m.get("url") or "").rstrip("/").rsplit("/", 1)[-1] or None
    row = {"slug": slug, "url": m.get("url")}
    scalar_fields = ("title", "year", "duration", "duration_s", "quality", "imdb", "poster", "synopsis", "updated_at")
    json_fields = ("genres", "actors", "director", "country", "embeds", "downloads")
    for key in scalar_fields:
        if key in m:
            row[key] = m.get(key)
    for key in json_fields:
        if key in m:
            row[key] = json.dumps(m.get(key) or [])
    if "is_series" in m:
        row["is_series"] = int(m.get("is_series") or 0)
    unified = {
        "source": "yomovies", "source_id": slug,
        "poster_url": m.get("poster"), "detail_url": m.get("url"),
        "player_kind": "hls",
    }
    if "is_hindi_dubbed" in m:
        unified["is_hindi_dubbed"] = int(m.get("is_hindi_dubbed") or 0)
    row.update({key: value for key, value in unified.items() if key in columns})
    row = {key: value for key, value in row.items() if key in columns}
    cols = ", ".join(row); ph = ", ".join("?" * len(row))
    upd = ", ".join(f"{c}=excluded.{c}" for c in row if c != "url")
    conflict_target = "source,source_id" if {"source", "source_id"}.issubset(columns) else "url"
    con.execute(f"INSERT INTO movies ({cols}) VALUES ({ph}) "
                f"ON CONFLICT({conflict_target}) DO UPDATE SET {upd}", list(row.values()))
    con.commit()


def set_meta(con, k: str, v: str) -> None:
    con.execute("INSERT INTO meta(k,v) VALUES(?,?) "
                "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v)); con.commit()


def get_meta(con, k: str) -> Optional[str]:
    r = con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r["v"] if r else None
