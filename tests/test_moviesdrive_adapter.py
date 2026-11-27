"""Unit tests for MoviesDrive adapter (new5.moviesdrive.cyou & moviesdrives.bid) and sync priority order."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

import app.sync as sync_mod
from app.adapters import registry
from app.adapters.moviesdrive import catalog
from app.adapters.moviesdrive.sync import sync_moviesdrive

SAMPLE_MD_LISTING = """
<html><body>
  <div class="movies-grid" id="moviesGridMain">
    <a href="https://new5.moviesdrive.cyou/gunmaaster-g9-2026-hq-hdtc-hindi-480p-720p-1080p-x264-esubs-full-movie/">
      <div class="poster-card">
        <div class="poster-image">
          <img src="https://image.tmdb.org/t/p/w400/vDYF2q48AIvBRpFiqKj6lKyM0p6.jpg" alt="Gunmaaster G9 (2026) HQ-HDTC [Hindi] 480p | 720p | 1080p [x264/ESubs] | Full Movie" />
          <span class="poster-quality">CAM</span>
        </div>
        <div class="poster-info">
          <p class="poster-title">Gunmaaster G9 (2026) HQ-HDTC [Hindi] 480p | 720p | 1080p [x264/ESubs] | Full Movie</p>
        </div>
      </div>
    </a>
    <a href="https://new5.moviesdrive.cyou/bigg-boss-season-20-2026/">
      <div class="poster-card">
        <div class="poster-image">
          <img src="https://image.tmdb.org/t/p/w500/k5ope1puShzLycqcj3FIoGAPjva.jpg" />
          <span class="poster-quality">FHD</span>
        </div>
        <div class="poster-info">
          <p class="poster-title">Bigg Boss (Season 20) 2026 [Hindi DD2.0] (S20 Ep83 Added) JioHotstar Series 480p 720p 1080p – WEB-DL</p>
        </div>
      </div>
    </a>
  </div>
</body></html>
"""

SAMPLE_MD_DETAIL = """
<html>
  <head>
    <title>Gunmaaster G9 (2026) HQ-HDTC – MoviesDrive</title>
    <meta name="description" content="Gunmaaster G9 action thriller movie." />
    <meta property="og:image" content="https://image.tmdb.org/t/p/w400/vDYF2q48AIvBRpFiqKj6lKyM0p6.jpg" />
  </head>
  <body>
    <p>IMDb: tt37539573</p>
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
            quality TEXT,
            best_quality TEXT,
            imdb TEXT,
            language TEXT,
            language_code TEXT,
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
            last_quality_upgrade_at INTEGER,
            is_hindi_dubbed INTEGER DEFAULT 0,
            UNIQUE(source, source_id)
        )
        """
    )
    conn.commit()
    conn.close()


class TestMoviesDriveAdapter(unittest.TestCase):
    def test_01_registry_and_parse_listing_and_detail(self):
        ad = registry.get("moviesdrive")
        self.assertIsNotNone(ad)
        self.assertEqual(ad.key, "moviesdrive")

        items = catalog.parse_listing(SAMPLE_MD_LISTING)
        self.assertEqual(len(items), 2)
        by_id = {i.source_id: i for i in items}

        gm = by_id["gunmaaster-g9-2026-hq-hdtc-hindi-480p-720p-1080p-x264-esubs-full-movie"]
        self.assertEqual(gm.title, "Gunmaaster G9")
        self.assertEqual(gm.year, 2026)
        self.assertFalse(gm.is_series)
        self.assertEqual(gm.language_code, "hi")
        self.assertEqual(getattr(gm, "quality"), "CAM")

        bb = by_id["bigg-boss-season-20-2026"]
        self.assertEqual(bb.title, "Bigg Boss (Season 20)")
        self.assertEqual(bb.year, 2026)
        self.assertTrue(bb.is_series)
        self.assertIn("Hotstar", json.loads(bb.genres))
        self.assertIn(getattr(bb, "quality"), ("1080p", "WEB-DL"))

        dinfo = catalog.parse_detail(SAMPLE_MD_DETAIL, gm.detail_url)
        self.assertEqual(dinfo["imdb"], "tt37539573")
        self.assertIn("Gunmaaster G9", dinfo["synopsis"])

    def test_02_sync_moviesdrive_insert_refresh_and_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test_md.sqlite3")
            _create_test_db(db_path)

            sess = _FakeSession({
                "https://new5.moviesdrive.cyou/": SAMPLE_MD_LISTING,
                "https://moviesdrives.bid/": "<html><title>Guide</title></html>",
                "https://new5.moviesdrive.cyou/gunmaaster-g9-2026-hq-hdtc-hindi-480p-720p-1080p-x264-esubs-full-movie/": SAMPLE_MD_DETAIL,
            })

            def fake_primary(title, year):
                del year
                return "bigg boss" in (title or "").lower()

            with mock.patch("app.api.routes_catalog.is_movie_available_on_primary_sources", side_effect=fake_primary):
                r1 = sync_moviesdrive(base_time=1796000000, pages_per_mirror=1, db_paths=[db_path], session=sess)
                r2 = sync_moviesdrive(base_time=1796000100, pages_per_mirror=1, db_paths=[db_path], session=sess)

            self.assertEqual(r1["added"], 1)
            self.assertEqual(r1["skipped"], 1)
            self.assertEqual(r2["added"], 0)
            self.assertEqual(r2["updated"], 1)

            conn = sqlite3.connect(db_path)
            rows = conn.execute("SELECT source, title, year, imdb, quality, is_hindi_dubbed FROM movies").fetchall()
            conn.close()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0], ("moviesdrive", "Gunmaaster G9", "2026", "tt37539573", "CAM", 1))

    def test_03_run_full_sync_checks_moviesdrive_immediately_after_yomovies(self):
        order: list[str] = []
        fake_notifier = mock.MagicMock()
        fake_notifier.send_sync_report.return_value = mock.MagicMock(sent=False, skipped=True, reason="disabled")

        with (
            mock.patch.object(sync_mod, "sync_yomovies", side_effect=lambda *a, **kw: (order.append("yomovies"), {"added": 0, "updated": 0, "total": 0})[1]),
            mock.patch.object(sync_mod, "sync_moviesdrive", side_effect=lambda *a, **kw: (order.append("moviesdrive"), {"added": 2, "updated": 1, "skipped": 0, "total": 3})[1]),
            mock.patch.object(sync_mod, "sync_ask4movie", side_effect=lambda *a, **kw: (order.append("ask4movie"), {"added": 0, "updated": 0, "total": 0})[1]),
            mock.patch.object(sync_mod, "sync_movies7", side_effect=lambda *a, **kw: (order.append("movies7"), {"added": 0, "updated": 0, "skipped": 0, "total": 0})[1]),
            mock.patch.object(sync_mod, "sync_dooflix", side_effect=lambda *a, **kw: (order.append("dooflix"), {"added": 0, "updated": 0, "skipped": 0, "total": 0})[1]),
            mock.patch.object(sync_mod, "sync_flixmovie", side_effect=lambda *a, **kw: (order.append("flixmovie"), {"added": 0, "updated": 0, "skipped": 0, "total": 0})[1]),
        ):
            summary = sync_mod.run_full_sync(notifier=fake_notifier)

        self.assertEqual(order[:2], ["yomovies", "moviesdrive"])
        self.assertEqual(order, list(registry.ADAPTERS.keys()))
        self.assertEqual(summary["moviesdrive"]["added"], 2)


if __name__ == "__main__":
    unittest.main()
