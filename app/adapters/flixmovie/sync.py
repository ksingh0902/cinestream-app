"""Sync & ingestion engine for FlixMovie (https://flixmovie.cc)."""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional

import requests

from ..base import MediaItem
from ..embed_helper import enrich_stream_servers
from . import catalog

logger = logging.getLogger("flixmovie.sync")


def get_target_db_paths() -> List[str]:
    paths: List[str] = []
    if os.path.exists("cinemymovies.sqlite3"):
        paths.append("cinemymovies.sqlite3")
    if os.path.exists("yomovies.db"):
        paths.append("yomovies.db")
    if not paths:
        paths.append("cinemymovies.sqlite3")
    return paths


def _slugify(text: str) -> str:
    s = (text or "").lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s or "title"


def upsert_item(conn: sqlite3.Connection, item: MediaItem, *, updated_at: Optional[int] = None) -> bool:
    """Upsert a FlixMovie item into movies. Returns True if newly inserted, False if updated."""
    now = int(updated_at or time.time())
    columns = {r[1] for r in conn.execute("PRAGMA table_info(movies)").fetchall()}

    existing = conn.execute(
        "SELECT id FROM movies WHERE source = 'flixmovie' AND source_id = ? LIMIT 1",
        (item.source_id,),
    ).fetchone()
    is_new = existing is None

    primary_url, servers = enrich_stream_servers(
        primary_url=item.detail_url or "",
        is_series=bool(item.is_series),
        tmdb_id=str(item.tmdb_id) if item.tmdb_id else None,
        season="1",
        episode="1",
        source="flixmovie",
    )

    genres_val = item.genres or "[]"
    if isinstance(genres_val, list):
        genres_val = json.dumps(genres_val)

    slug = f"fm-{_slugify(item.title)}-{item.source_id}"
    data: Dict[str, Any] = {
        "source": "flixmovie",
        "source_id": item.source_id,
        "slug": slug,
        "title": item.title,
        "year": str(item.year) if item.year else None,
        "poster_url": item.poster_url,
        "poster": item.poster_url,
        "rating": item.rating,
        "genres": genres_val,
        "synopsis": item.synopsis or "",
        "tmdb_id": item.tmdb_id,
        "is_series": 1 if item.is_series else 0,
        "detail_url": item.detail_url,
        "url": item.detail_url,
        "player_kind": item.player_kind or "iframe",
        "player_url": primary_url,
        "servers_json": json.dumps(servers),
        "resolved_at": now,
        "updated_at": now,
        "is_hindi_dubbed": 0,
    }
    if "first_added_at" in columns and is_new:
        data["first_added_at"] = now
    if "last_checked_at" in columns:
        data["last_checked_at"] = now
    if "last_updated_at" in columns:
        data["last_updated_at"] = now

    filtered = {k: v for k, v in data.items() if k in columns}
    cols = ", ".join(filtered.keys())
    placeholders = ", ".join(f":{k}" for k in filtered.keys())
    _PRESERVE_IF_NULL_COLS = {"tmdb_id", "poster_url", "poster", "rating", "year", "player_url", "servers_json"}
    update_parts: List[str] = []
    for k in filtered.keys():
        if k in ("source", "source_id", "slug", "first_added_at"):
            continue
        if k in _PRESERVE_IF_NULL_COLS:
            update_parts.append(f"{k}=COALESCE(excluded.{k}, movies.{k})")
        elif k == "synopsis":
            update_parts.append("synopsis=CASE WHEN excluded.synopsis != '' THEN excluded.synopsis ELSE movies.synopsis END")
        else:
            update_parts.append(f"{k}=excluded.{k}")
    update_clause = ", ".join(update_parts)

    conn.execute(
        f"INSERT INTO movies ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT(source, source_id) DO UPDATE SET {update_clause}",
        filtered,
    )
    return is_new


def sync_flixmovie(
    base_time: Optional[int] = None,
    *,
    pages_per_category: int = 2,
    enrich_details: bool = True,
    max_detail_enriches: int = 40,
    db_paths: Optional[List[str]] = None,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """Sync latest movies & TV shows from FlixMovie (https://flixmovie.cc) with cross-source dedup."""
    now = int(base_time or time.time())
    target_dbs = db_paths if db_paths is not None else get_target_db_paths()
    print(f"[sync-flixmovie] Scraping latest items from {catalog.FLIXMOVIE_BASE}...", flush=True)

    owns_session = session is None
    sess = session if session is not None else requests.Session()
    headers = {"User-Agent": catalog.DEFAULT_UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}

    added = 0
    updated = 0
    skipped = 0
    enriched = 0

    try:
        items = list(catalog.iter_catalog(max_pages=pages_per_category, session=sess))
        print(f"[sync-flixmovie] Discovered {len(items)} unique items from FlixMovie.", flush=True)

        conns = [sqlite3.connect(p, timeout=30) for p in target_dbs]
        try:
            for c in conns:
                c.execute("PRAGMA journal_mode=WAL")

            try:
                from ...api.routes_catalog import is_movie_available_on_primary_sources
            except Exception:
                is_movie_available_on_primary_sources = None

            for idx, it in enumerate(items):
                exists_any = any(
                    c.execute(
                        "SELECT 1 FROM movies WHERE source='flixmovie' AND source_id=? LIMIT 1",
                        (it.source_id,),
                    ).fetchone() is not None
                    for c in conns
                )

                if not exists_any and is_movie_available_on_primary_sources:
                    try:
                        if is_movie_available_on_primary_sources(it.title, it.year):
                            skipped += 1
                            continue
                    except Exception:
                        pass

                # Enrich newly discovered titles with TMDb ID / synopsis / high-res poster
                if enrich_details and not exists_any and enriched < max_detail_enriches and it.detail_url:
                    try:
                        rd = sess.get(it.detail_url, headers=headers, timeout=12, allow_redirects=True)
                        if rd.status_code == 200:
                            dinfo = catalog.parse_detail(rd.text, it.detail_url)
                            if dinfo.get("tmdb_id") and not it.tmdb_id:
                                it.tmdb_id = dinfo["tmdb_id"]
                            if dinfo.get("synopsis") and not it.synopsis:
                                it.synopsis = dinfo["synopsis"]
                            if dinfo.get("poster_url") and not it.poster_url:
                                it.poster_url = dinfo["poster_url"]
                            enriched += 1
                    except Exception as exc:
                        logger.debug("FlixMovie detail enrich failed for %s: %s", it.detail_url, exc)

                recency_ts = now - idx
                was_new_overall = False
                for c in conns:
                    if upsert_item(c, it, updated_at=recency_ts):
                        was_new_overall = True
                if was_new_overall:
                    added += 1
                else:
                    updated += 1

            for c in conns:
                c.commit()
        finally:
            for c in conns:
                c.close()
    finally:
        if owns_session:
            sess.close()

    print(
        f"[sync-flixmovie] Finished: {added} added, {updated} refreshed, {skipped} duplicates skipped (total={len(items)}).",
        flush=True,
    )
    return {
        "status": "success",
        "source": "flixmovie",
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "total": len(items),
    }
