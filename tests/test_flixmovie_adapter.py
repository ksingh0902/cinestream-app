"""Unit tests for FlixMovie adapter (https://flixmovie.cc)."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from app.adapters import registry
from app.adapters.flixmovie import catalog
from app.adapters.flixmovie.sync import sync_flixmovie

SAMPLE_HOME_HTML = """
<html><body>
  <div class="detail">
    <div class="genre"><a href="/genre/action">Action</a><a href="/genre/comedy">Comedy</a></div>
    <h2 class="title">Street Fighter</h2>
    <div class="metadata set">
      <span class="IMDb"><b>IMDb</b>6.2</span>
      <span class="quality">CAM</span>
      <span>120 min</span> <span>2026</span>
    </div>
    <p class="description">Ryu and Ken enter the World Warrior Tournament.</p>
    <div class="swiper-ctrl">
      <a class="btn btn-primary watch-btn" href="/watch/movie-street-fighter-h4871qxe">Watch Now</a>
    </div>
  </div>
  <a class="bf-card" href="/watch/tv-dexter-resurrection-dzey5x4q" title="Dexter: Resurrection - Season 2 (2026)">
    <img class="bf-card__img" src="https://image.tmdb.org/t/p/w342/dexter.jpg" />
    <span class="bf-card__name">Dexter: Resurrection - Season 2 (2026)</span>
    <span class="bf-card__genre">Crime, Drama</span>
  </a>
</body></html>
"""

SAMPLE_DETAIL_HTML = """
<html>
  <head>
    <title>Watch Street Fighter Movie Online - FlixMovie</title>
    <meta name="description" content="Full synopsis for Street Fighter." />
    <meta property="og:image" content="https://image.tmdb.org/t/p/w1280/zDE9hd1SG9695YncbZGjSf7Z9Jk.jpg" />
  </head>
  <body>
    <div data-id="1153576"></div>
  </body>
</html>
"""


class _FakeResp:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class _FakeSession:
    def __init__(self, routes: dict[str, str]):
        self._routes = routes

    def get(self, url: str, headers=None, timeout=None, allow_redirects=True):
        del headers, timeout, allow_redirects
        if url in self._routes:
            return _FakeResp(200, self._routes[url])
        return _FakeResp(404, "")

    def close(self) -> None:
        pass


def _create_test_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_id TEXT NOT NULL,
            slug TEXT,
            title TEXT,
            year TEXT,
            poster_url TEXT,
            poster TEXT,
            rating REAL,
            genres TEXT,
            synopsis TEXT,
            tmdb_id INTEGER,
            is_series INTEGER DEFAULT 0,
            detail_url TEXT,
            url TEXT,
            player_kind TEXT,
            player_url TEXT,
            servers_json TEXT,
            resolved_at INTEGER,
            updated_at INTEGER,
            first_added_at INTEGER,
            last_checked_at INTEGER,
            last_updated_at INTEGER,
            is_hindi_dubbed INTEGER DEFAULT 0,
            UNIQUE(source, source_id)
        )
        """
    )
    conn.commit()
    conn.close()


class TestFlixMovieAdapter(unittest.TestCase):
    def test_01_registry_and_parse_listing_and_detail(self):
        ad = registry.get("flixmovie")
        self.assertIsNotNone(ad)
        self.assertEqual(ad.key, "flixmovie")

        items = catalog.parse_listing(SAMPLE_HOME_HTML)
        self.assertEqual(len(items), 2)
        by_id = {i.source_id: i for i in items}
        self.assertIn("tv-dexter-resurrection-dzey5x4q", by_id)
        self.assertTrue(by_id["tv-dexter-resurrection-dzey5x4q"].is_series)
        self.assertEqual(by_id["tv-dexter-resurrection-dzey5x4q"].title, "Dexter: Resurrection")
        self.assertEqual(by_id["tv-dexter-resurrection-dzey5x4q"].year, 2026)

        self.assertIn("movie-street-fighter-h4871qxe", by_id)
        self.assertFalse(by_id["movie-street-fighter-h4871qxe"].is_series)
        self.assertEqual(by_id["movie-street-fighter-h4871qxe"].rating, 6.2)

        dinfo = catalog.parse_detail(SAMPLE_DETAIL_HTML, "https://flixmovie.cc/watch/movie-street-fighter-h4871qxe")
        self.assertEqual(dinfo["tmdb_id"], 1153576)
        self.assertIn("Street Fighter", dinfo["synopsis"])
        self.assertIn("image.tmdb.org", dinfo["poster_url"])

    def test_02_sync_flixmovie_insert_refresh_and_cross_source_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test_fm.sqlite3")
            _create_test_db(db_path)

            sess = _FakeSession({
                "https://flixmovie.cc/home": SAMPLE_HOME_HTML,
                "https://flixmovie.cc/watch/movie-street-fighter-h4871qxe": SAMPLE_DETAIL_HTML,
            })

            # Mark Street Fighter as NOT on primary sources, Dexter as already on primary sources -> 1 added, 1 skipped
            def fake_primary(title, year):
                del year
                return "dexter" in (title or "").lower()

            with mock.patch("app.api.routes_catalog.is_movie_available_on_primary_sources", side_effect=fake_primary):
                res1 = sync_flixmovie(base_time=1796000000, pages_per_category=1, db_paths=[db_path], session=sess)
                res2 = sync_flixmovie(base_time=1796000100, pages_per_category=1, db_paths=[db_path], session=sess)

            self.assertEqual(res1["added"], 1)
            self.assertEqual(res1["skipped"], 1)
            self.assertEqual(res2["added"], 0)
            self.assertEqual(res2["updated"], 1)

            conn = sqlite3.connect(db_path)
            rows = conn.execute("SELECT source, source_id, title, tmdb_id, servers_json FROM movies").fetchall()
            conn.close()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "flixmovie")
            self.assertEqual(rows[0][1], "movie-street-fighter-h4871qxe")
            self.assertEqual(rows[0][3], 1153576)
            self.assertTrue(len(json.loads(rows[0][4])) >= 1)


if __name__ == "__main__":
    unittest.main()
