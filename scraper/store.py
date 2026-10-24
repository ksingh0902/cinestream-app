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
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def connect(path: str = "yomovies.db") -> sqlite3.Connection:
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA); con.commit()
    return con


def upsert(con, m: Dict) -> None:
    row = {
        "slug": (m.get("url") or "").rstrip("/").rsplit("/", 1)[-1] or None,
        "url": m.get("url"), "title": m.get("title"), "year": m.get("year"),
        "duration": m.get("duration"), "duration_s": m.get("duration_s"),
        "quality": m.get("quality"), "imdb": m.get("imdb"),
        "genres": json.dumps(m.get("genres") or []),
        "actors": json.dumps(m.get("actors") or []),
        "director": json.dumps(m.get("director") or []),
        "country": json.dumps(m.get("country") or []),
        "poster": m.get("poster"), "synopsis": m.get("synopsis"),
        "is_series": int(m.get("is_series") or 0),
        "embeds": json.dumps(m.get("embeds") or []),
        "downloads": json.dumps(m.get("downloads") or []),
        "updated_at": m.get("updated_at"),
    }
    cols = ", ".join(row); ph = ", ".join("?" * len(row))
    upd = ", ".join(f"{c}=excluded.{c}" for c in row if c != "url")
    con.execute(f"INSERT INTO movies ({cols}) VALUES ({ph}) "
                f"ON CONFLICT(url) DO UPDATE SET {upd}", list(row.values()))
    con.commit()


def set_meta(con, k: str, v: str) -> None:
    con.execute("INSERT INTO meta(k,v) VALUES(?,?) "
                "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v)); con.commit()


def get_meta(con, k: str) -> Optional[str]:
    r = con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r["v"] if r else None
