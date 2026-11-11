"""SQLite persistence. Only stable facts are stored (R1)."""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Dict, Optional

from app.catalogue.quality import is_quality_upgrade

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
    now = int(time.time())
    if "first_added_at" in columns:
        row["first_added_at"] = now
    if "last_checked_at" in columns:
        row["last_checked_at"] = now
    if "last_updated_at" in columns:
        row["last_updated_at"] = now

    conflict_target = "source,source_id" if {"source", "source_id"}.issubset(columns) else "url"
    source_val = row.get("source") or "yomovies"
    source_id_val = row.get("source_id") or slug
    old_row = None
    if conflict_target == "source,source_id" and source_val and source_id_val:
        old_row = con.execute("SELECT id, quality, best_quality, first_added_at FROM movies WHERE source = ? AND source_id = ?", (source_val, source_id_val)).fetchone()
    if not old_row and row.get("url"):
        old_row = con.execute("SELECT id, quality, best_quality, first_added_at FROM movies WHERE url = ?", (row["url"],)).fetchone()

    if old_row:
        if "first_added_at" in columns and old_row["first_added_at"]:
            row["first_added_at"] = old_row["first_added_at"]

        new_q = m.get("quality")
        is_upg, badge = is_quality_upgrade(old_row["quality"], new_q)
        if is_upg and badge:
            if "last_quality_upgrade_at" in columns:
                row["last_quality_upgrade_at"] = now
            if "latest_quality_transition" in columns:
                row["latest_quality_transition"] = badge
            if "best_quality" in columns:
                row["best_quality"] = new_q
            try:
                con.execute(
                    "INSERT INTO quality_history (movie_id, old_quality, new_quality, transition_badge, upgraded_at) VALUES (?, ?, ?, ?, ?)",
                    (old_row["id"], old_row["quality"], new_q, badge, now)
                )
            except Exception:
                pass

    row = {key: value for key, value in row.items() if key in columns}
    cols = ", ".join(row); ph = ", ".join("?" * len(row))
    upd_parts = []
    for c in row:
        if c == "url":
            continue
        if c == "first_added_at":
            upd_parts.append("first_added_at=COALESCE(movies.first_added_at, excluded.first_added_at)")
        elif c == "last_quality_upgrade_at":
            upd_parts.append("last_quality_upgrade_at=COALESCE(excluded.last_quality_upgrade_at, movies.last_quality_upgrade_at)")
        elif c == "latest_quality_transition":
            upd_parts.append("latest_quality_transition=COALESCE(excluded.latest_quality_transition, movies.latest_quality_transition)")
        else:
            upd_parts.append(f"{c}=excluded.{c}")
    upd = ", ".join(upd_parts)
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
