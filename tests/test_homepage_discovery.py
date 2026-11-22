"""Comprehensive backend unit & integration tests for CINEMY Homepage Catalogue Sections & Date-Based Discovery."""
from __future__ import annotations

import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import shutil
import sqlite3
import tempfile
import time
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_catalog import router as catalog_router
from app.catalogue.quality import parse_quality_tier, is_quality_upgrade
from app.db.migrate import migrate_database
from scraper.store import connect, upsert


class TestHomepageDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="cinemy_test_")
        cls.db_path = os.path.join(cls.temp_dir, "test_catalogue.db")

        # Set DB_PATH environment variable for route handlers
        os.environ["DB_PATH"] = cls.db_path

        # Initialize base schema and run migrations
        con = connect(cls.db_path)
        con.close()
        migrate_database(cls.db_path)

        # Setup test FastAPI app
        cls.app = FastAPI()
        cls.app.include_router(catalog_router)
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)
        if "DB_PATH" in os.environ:
            del os.environ["DB_PATH"]

    def _get_con(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    # --- Scenario 1: Newly discovered title appears in Recently Added ---
    def test_01_newly_discovered_title_appears_in_recently_added(self):
        con = self._get_con()
        now = int(time.time())
        m = {
            "url": "https://example.com/movie/test-new-title-1",
            "title": "Brand New Discovery 2026",
            "year": "2026",
            "quality": "1080p",
            "is_series": 0,
            "poster": "https://example.com/p1.jpg",
            "genres": ["Action", "Sci-Fi"],
        }
        upsert(con, m)
        con.close()

        resp = self.client.get("/api/catalog/recently-added?limit=20&window_months=3")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        titles = [item["title"] for item in data["items"]]
        self.assertIn("Brand New Discovery 2026", titles)

        # Verify item fields
        found = next(i for i in data["items"] if i["title"] == "Brand New Discovery 2026")
        self.assertEqual(found["year"], "2026")
        self.assertEqual(found["quality"], "1080p")
        self.assertIsNotNone(found.get("first_added_at"))

    # --- Scenario 2: Existing title crawled again does not reset first_added_at ---
    def test_02_recrawled_title_preserves_first_added_at(self):
        con = self._get_con()
        past_time = int(time.time()) - (45 * 86400)  # 45 days ago
        m = {
            "url": "https://example.com/movie/test-stable-title-2",
            "title": "Stable Discovery 2025",
            "year": "2025",
            "quality": "720p",
            "is_series": 0,
        }
        upsert(con, m)

        # Manually backdate first_added_at
        con.execute("UPDATE movies SET first_added_at = ? WHERE url = ?", (past_time, m["url"]))
        con.commit()

        row_before = con.execute("SELECT first_added_at, updated_at FROM movies WHERE url = ?", (m["url"],)).fetchone()
        self.assertEqual(row_before["first_added_at"], past_time)

        # Re-crawl with updated synopsis and duration
        m_recrawl = dict(m)
        m_recrawl["synopsis"] = "Updated synopsis on routine refresh"
        m_recrawl["duration"] = "130 min"
        upsert(con, m_recrawl)

        row_after = con.execute("SELECT first_added_at, synopsis FROM movies WHERE url = ?", (m["url"],)).fetchone()
        con.close()

        # first_added_at must be preserved, while synopsis is updated
        self.assertEqual(row_after["first_added_at"], past_time)
        self.assertEqual(row_after["synopsis"], "Updated synopsis on routine refresh")

    # --- Scenario 3: Verified CAM-to-HD upgrade appears in Recently Upgraded with badge ---
    def test_03_cam_to_hd_upgrade_records_history_and_badge(self):
        con = self._get_con()
        url = "https://example.com/movie/cam-to-hd-upgrade"
        m_initial = {
            "url": url,
            "title": "Blockbuster Movie 2026",
            "year": "2026",
            "quality": "CAM",
            "is_series": 0,
            "poster": "https://example.com/poster.jpg",
        }
        upsert(con, m_initial)

        # Upgrade to HD
        m_upgraded = dict(m_initial)
        m_upgraded["quality"] = "HD"
        upsert(con, m_upgraded)

        # Check DB columns
        row = con.execute("SELECT quality, best_quality, latest_quality_transition, last_quality_upgrade_at FROM movies WHERE url = ?", (url,)).fetchone()
        self.assertEqual(row["quality"], "HD")
        self.assertEqual(row["best_quality"], "HD")
        self.assertEqual(row["latest_quality_transition"], "CAM → HD")
        self.assertIsNotNone(row["last_quality_upgrade_at"])

        # Check quality_history table
        hist = con.execute("SELECT * FROM quality_history WHERE transition_badge = 'CAM → HD'").fetchone()
        self.assertIsNotNone(hist)
        self.assertEqual(hist["old_quality"], "CAM")
        self.assertEqual(hist["new_quality"], "HD")
        con.close()

        # Check API endpoint
        resp = self.client.get("/api/catalog/recently-upgraded?limit=20&window_months=3")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        item = next((i for i in data["items"] if i["title"] == "Blockbuster Movie 2026"), None)
        self.assertIsNotNone(item)
        self.assertEqual(item.get("upgradeBadge"), "CAM → HD")

    # --- Scenario 4: Routine source refresh does not count as upgrade ---
    def test_04_routine_source_refresh_does_not_count_as_upgrade(self):
        con = self._get_con()
        url = "https://example.com/movie/routine-refresh-title"
        m = {
            "url": url,
            "title": "Routine Refresh Film",
            "year": "2025",
            "quality": "1080p",
            "is_series": 0,
        }
        upsert(con, m)

        initial_count = con.execute("SELECT COUNT(*) as c FROM quality_history").fetchone()["c"]

        # Routine refresh: same quality
        upsert(con, m)

        after_count = con.execute("SELECT COUNT(*) as c FROM quality_history").fetchone()["c"]
        self.assertEqual(initial_count, after_count)

        row = con.execute("SELECT latest_quality_transition, last_quality_upgrade_at FROM movies WHERE url = ?", (url,)).fetchone()
        con.close()
        self.assertIsNone(row["latest_quality_transition"])
        self.assertIsNone(row["last_quality_upgrade_at"])

    # --- Scenario 5: Quality downgrade does not count as upgrade ---
    def test_05_quality_downgrade_does_not_count_as_upgrade(self):
        # Test quality hierarchy logic
        is_upg, badge = is_quality_upgrade("1080p", "720p")
        self.assertFalse(is_upg)
        self.assertIsNone(badge)

        is_upg2, badge2 = is_quality_upgrade("HD", "CAM")
        self.assertFalse(is_upg2)
        self.assertIsNone(badge2)

        # Test through store upsert
        con = self._get_con()
        url = "https://example.com/movie/downgrade-check-title"
        m = {
            "url": url,
            "title": "Downgrade Check Film",
            "year": "2025",
            "quality": "1080p",
            "is_series": 0,
        }
        upsert(con, m)

        # Attempt to upsert with inferior quality
        m_lower = dict(m)
        m_lower["quality"] = "CAM"
        upsert(con, m_lower)

        row = con.execute("SELECT latest_quality_transition, last_quality_upgrade_at FROM movies WHERE url = ?", (url,)).fetchone()
        con.close()
        self.assertIsNone(row["latest_quality_transition"])
        self.assertIsNone(row["last_quality_upgrade_at"])

    # --- Scenario 6: Duplicate titles do not produce duplicate cards ---
    def test_06_duplicate_titles_deduplicated_in_recently_added(self):
        con = self._get_con()
        now = int(time.time())
        m1 = {
            "url": "https://example.com/movie/dup-title-source-1",
            "title": "Gladiator II (2024)",
            "year": "2024",
            "quality": "HD",
            "is_series": 0,
            "poster": "https://example.com/poster.jpg",
        }
        m2 = {
            "url": "https://example.com/movie/dup-title-source-2",
            "title": "Gladiator II [2024]",
            "year": "2024",
            "quality": "1080p",
            "is_series": 0,
            "poster": "https://example.com/poster.jpg",
        }
        upsert(con, m1)
        upsert(con, m2)
        con.close()

        resp = self.client.get("/api/catalog/recently-added?limit=50&window_months=3")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["items"]
        glad_items = [i for i in items if "Gladiator II" in i["title"]]
        # Should be de-duplicated to exactly 1 card
        self.assertEqual(len(glad_items), 1)

    # --- Scenario 7: Release year and first-added date remain independent ---
    def test_07_release_year_and_first_added_date_independent(self):
        con = self._get_con()
        # Classic 1994 movie added today
        m = {
            "url": "https://example.com/movie/classic-shawshank-1994",
            "title": "The Shawshank Redemption",
            "year": "1994",
            "quality": "BluRay",
            "is_series": 0,
            "poster": "https://example.com/poster.jpg",
        }
        upsert(con, m)
        con.close()

        # 1. It must appear in Recently Added (first_added_at is today)
        resp_recent = self.client.get("/api/catalog/recently-added?limit=50&window_months=3")
        recent_titles = [i["title"] for i in resp_recent.json()["items"]]
        self.assertIn("The Shawshank Redemption", recent_titles)

        # 2. In /api/catalog/years, 1994 is tracked under older_count (or specific year if top 8)
        resp_years = self.client.get("/api/catalog/years")
        self.assertEqual(resp_years.status_code, 200)
        data = resp_years.json()
        self.assertIn("years", data)
        self.assertGreater(data.get("older_count", 0), 0)

    # --- Scenario 8: Titles outside configured time window are excluded ---
    def test_08_titles_outside_time_window_excluded(self):
        con = self._get_con()
        url = "https://example.com/movie/ancient-added-title"
        # 120 days ago (approx 4 months, outside 3 months default)
        old_time = int(time.time()) - (120 * 86400)
        m = {
            "url": url,
            "title": "Old Ingestion Movie",
            "year": "2023",
            "quality": "HD",
            "is_series": 0,
            "poster": "https://example.com/poster.jpg",
        }
        upsert(con, m)
        con.execute("UPDATE movies SET first_added_at = ? WHERE url = ?", (old_time, url))
        con.commit()
        con.close()

        # Query with 3-month window
        resp = self.client.get("/api/catalog/recently-added?limit=50&window_months=3")
        titles = [i["title"] for i in resp.json()["items"]]
        self.assertNotIn("Old Ingestion Movie", titles)

        # Query with 5-month window
        resp_wide = self.client.get("/api/catalog/recently-added?limit=50&window_months=5")
        titles_wide = [i["title"] for i in resp_wide.json()["items"]]
        self.assertIn("Old Ingestion Movie", titles_wide)

    # --- Scenario 9: Empty discovery sections render valid empty response ---
    def test_09_empty_discovery_sections_valid_response(self):
        # Filter for series=1 when no series have undergone quality upgrades
        resp = self.client.get("/api/catalog/recently-upgraded?series=1&window_months=3")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total"], 0)

    # --- Scenario 10: Homepage preferences API ---
    def test_10_homepage_preferences_api(self):
        resp = self.client.get("/api/homepage/preferences")
        self.assertEqual(resp.status_code, 200)
        prefs = resp.json()
        self.assertIn("recently_added_enabled", prefs)
        self.assertIn("recently_upgraded_enabled", prefs)
        self.assertIn("recently_added_window_months", prefs)
        self.assertIn("recently_upgraded_window_months", prefs)
        self.assertIn("default_sort", prefs)
        self.assertIn("allowed_qualities", prefs)

    # --- Scenario 11: Movie and series filtering continues to work ---
    def test_11_media_type_and_quality_filtering(self):
        con = self._get_con()
        upsert(con, {
            "url": "https://example.com/series/test-series-1",
            "title": "Epic Series Season 1",
            "year": "2026",
            "quality": "1080p",
            "is_series": 1,
            "genres": ["Drama"],
        })
        upsert(con, {
            "url": "https://example.com/movie/test-movie-filter-1",
            "title": "Epic Feature Film",
            "year": "2026",
            "quality": "4K",
            "is_series": 0,
            "genres": ["Action"],
        })
        con.close()

        # Filter movies only
        resp_m = self.client.get("/api/movies?media_type=movie&search=Epic")
        self.assertEqual(resp_m.status_code, 200)
        data_m = resp_m.json()
        for item in data_m.get("movies", []):
            self.assertEqual(item.get("is_series", 0), 0)

        # Filter series only
        resp_s = self.client.get("/api/movies?media_type=series&search=Epic")
        self.assertEqual(resp_s.status_code, 200)
        data_s = resp_s.json()
        for item in data_s.get("movies", []):
            self.assertEqual(item.get("is_series", 0), 1)

        # Filter by quality 4K
        resp_q = self.client.get("/api/movies?quality=4K")
        self.assertEqual(resp_q.status_code, 200)
        data_q = resp_q.json()
        for item in data_q.get("movies", []):
            self.assertEqual(item.get("quality"), "4K")

    # --- Scenario 12: latest_crawl=true excludes older crawl batches ---
    def test_12_recently_added_latest_crawl_only(self):
        con = connect(self.db_path)
        now = int(time.time())
        stale_ts = now - (10 * 86400)  # 10 days ago (still within 3 months, but not latest crawl)
        url_stale = "https://example.com/movie/stale-crawl-item"
        url_fresh = "https://example.com/movie/fresh-crawl-item"

        upsert(con, {
            "url": url_stale,
            "title": "Stale Crawl Title",
            "year": "2026",
            "quality": "HD",
            "is_series": 0,
            "source": "dooflix",
            "poster": "https://example.com/stale.jpg",
        })
        con.execute("UPDATE movies SET first_added_at = ?, updated_at = ? WHERE url = ?", (stale_ts, stale_ts, url_stale))

        upsert(con, {
            "url": url_fresh,
            "title": "Fresh Crawl Title",
            "year": "2026",
            "quality": "HD",
            "is_series": 0,
            "source": "yomovies",
            "poster": "https://example.com/fresh.jpg",
        })
        con.execute("UPDATE movies SET first_added_at = ?, updated_at = ? WHERE url = ?", (now, now, url_fresh))
        con.commit()
        con.close()

        resp = self.client.get("/api/catalog/recently-added?limit=30&window_months=3&latest_crawl=true")
        self.assertEqual(resp.status_code, 200)
        titles = [i["title"] for i in resp.json()["items"]]
        self.assertIn("Fresh Crawl Title", titles)
        self.assertNotIn("Stale Crawl Title", titles)


class TestRecentlyAddedSourcePriorityAndPagination(unittest.TestCase):
    """Tests for Recently Added YoMovies first-10 source priority, deduplication, and 75-item pagination."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cinemy_ra_test_")
        self.db_path = os.path.join(self.temp_dir, "test_ra.db")
        self._prev_db_path = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = self.db_path

        con = connect(self.db_path)
        con.close()
        migrate_database(self.db_path)

        from app.api.routes_catalog import invalidate_catalog_cache
        invalidate_catalog_cache()

        self.app = FastAPI()
        self.app.include_router(catalog_router)
        self.client = TestClient(self.app)

    def tearDown(self):
        from app.api.routes_catalog import invalidate_catalog_cache
        invalidate_catalog_cache()
        if self._prev_db_path is not None:
            os.environ["DB_PATH"] = self._prev_db_path
        elif "DB_PATH" in os.environ:
            del os.environ["DB_PATH"]
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _seed_item(self, con, idx: int, source: str, title: str, year: str = "2026", first_added_at: int | None = None):
        ts = first_added_at if first_added_at is not None else int(time.time()) - idx
        url = f"https://example.com/{source}/item-{idx}"
        upsert(con, {
            "url": url,
            "title": title,
            "year": year,
            "quality": "1080p",
            "is_series": 0,
            "source": source,
            "poster": f"https://example.com/poster-{idx}.jpg",
        })
        con.execute(
            "UPDATE movies SET source = ?, first_added_at = ?, updated_at = ? WHERE url = ?",
            (source, ts, ts, url),
        )

    def test_source_priority_first_10_yomovies_and_remaining_other_sources(self):
        con = connect(self.db_path)
        now = int(time.time())
        for i in range(15):
            self._seed_item(con, i, "yomovies", f"YoMovies Title {i:02d}", year="2026", first_added_at=now - i)
        # Add an unknown-year YoMovies item with newer timestamp: must NOT outrank 2026 releases
        self._seed_item(con, 99, "yomovies", "Unknown Year YoTitle", year="", first_added_at=now + 500)
        for i in range(20):
            src = ["dooflix", "ask4movie", "movies7"][i % 3]
            self._seed_item(con, 200 + i, src, f"Other Source Title {i:02d}", year="2026", first_added_at=now - i)
        con.commit()
        con.close()

        # Check /api/movies?sort=first_added&page=1&per_page=75
        resp = self.client.get("/api/movies?sort=first_added&page=1&per_page=75")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["items"]
        self.assertEqual(len(items), 36)

        first_10 = items[:10]
        self.assertTrue(all(it["source"] == "yomovies" for it in first_10))
        self.assertNotIn("Unknown Year YoTitle", [it["title"] for it in first_10])

        # Positions 11..30 must come from other sources before remaining yomovies
        positions_11_to_30 = items[10:30]
        self.assertTrue(all(it["source"] != "yomovies" for it in positions_11_to_30))
        self.assertIn("dooflix", {it["source"] for it in positions_11_to_30})
        self.assertIn("ask4movie", {it["source"] for it in positions_11_to_30})

        # Also check /api/catalog/recently-added
        ra_resp = self.client.get("/api/catalog/recently-added?limit=30&window_months=3")
        self.assertEqual(ra_resp.status_code, 200)
        ra_items = ra_resp.json()["items"]
        self.assertEqual(len(ra_items), 30)
        self.assertTrue(all(it["source"] == "yomovies" for it in ra_items[:10]))
        self.assertTrue(any(it["source"] != "yomovies" for it in ra_items[10:]))

    def test_fewer_than_10_yomovies_fills_from_other_sources_without_gaps(self):
        con = connect(self.db_path)
        now = int(time.time())
        for i in range(4):
            self._seed_item(con, i, "yomovies", f"Yo Short {i}", year="2026", first_added_at=now - i)
        for i in range(12):
            src = "dooflix" if i % 2 == 0 else "ask4movie"
            self._seed_item(con, 100 + i, src, f"Other Fill {i}", year="2026", first_added_at=now - i)
        con.commit()
        con.close()

        resp = self.client.get("/api/movies?sort=first_added&page=1&per_page=75")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        items = data["items"]
        self.assertEqual(len(items), 16)
        self.assertFalse(data["has_more"])
        self.assertTrue(all(it["source"] == "yomovies" for it in items[:4]))
        self.assertTrue(all(it["source"] != "yomovies" for it in items[4:]))

    def test_canonical_deduplication_across_yomovies_and_other_sources(self):
        con = connect(self.db_path)
        now = int(time.time())
        self._seed_item(con, 1, "yomovies", "Shared Blockbuster (2026)", year="2026", first_added_at=now)
        self._seed_item(con, 2, "dooflix", "Shared Blockbuster [2026] Hindi Dubbed", year="2026", first_added_at=now + 10)
        self._seed_item(con, 3, "ask4movie", "Shared Blockbuster", year="2026", first_added_at=now + 20)
        self._seed_item(con, 4, "dooflix", "Unique DooFlix Film", year="2026", first_added_at=now - 5)
        con.commit()
        con.close()

        resp = self.client.get("/api/movies?sort=first_added&page=1&per_page=75")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["items"]
        shared = [it for it in items if "Shared Blockbuster" in it["title"]]
        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0]["source"], "yomovies")
        self.assertEqual(len(items), 2)

    def test_pagination_75_per_page_multi_page_and_exact_75_boundary(self):
        con = connect(self.db_path)
        now = int(time.time())
        # Seed 15 YoMovies + 145 other-source titles = 160 total unique titles
        for i in range(15):
            self._seed_item(con, i, "yomovies", f"Paginated Yo {i:03d}", year="2026", first_added_at=now - i)
        for i in range(145):
            src = "dooflix" if i % 2 == 0 else "ask4movie"
            self._seed_item(con, 500 + i, src, f"Paginated Other {i:03d}", year="2026", first_added_at=now - i)
        con.commit()
        con.close()

        p1 = self.client.get("/api/movies?sort=first_added&page=1&per_page=75").json()
        p2 = self.client.get("/api/movies?sort=first_added&page=2&per_page=75").json()
        p3 = self.client.get("/api/movies?sort=first_added&page=3&per_page=75").json()

        self.assertEqual(len(p1["items"]), 75)
        self.assertTrue(p1["has_more"])
        self.assertTrue(all(it["source"] == "yomovies" for it in p1["items"][:10]))
        self.assertTrue(all(it["source"] != "yomovies" for it in p1["items"][10:]))

        self.assertEqual(len(p2["items"]), 75)
        self.assertTrue(p2["has_more"])

        self.assertEqual(len(p3["items"]), 10)
        self.assertFalse(p3["has_more"])

        all_ids = [it["id"] for it in (p1["items"] + p2["items"] + p3["items"])]
        self.assertEqual(len(all_ids), 160)
        self.assertEqual(len(set(all_ids)), 160)

    def test_exactly_75_titles_hides_has_more(self):
        con = connect(self.db_path)
        now = int(time.time())
        for i in range(10):
            self._seed_item(con, i, "yomovies", f"Exact75 Yo {i:02d}", year="2026", first_added_at=now - i)
        for i in range(65):
            self._seed_item(con, 200 + i, "dooflix", f"Exact75 Other {i:02d}", year="2026", first_added_at=now - i)
        con.commit()
        con.close()

        p1 = self.client.get("/api/movies?sort=first_added&page=1&per_page=75").json()
        self.assertEqual(len(p1["items"]), 75)
        self.assertEqual(p1["total"], 75)
        self.assertFalse(p1["has_more"])

    def test_latest_crawl_still_prioritizes_first_10_yomovies_when_latest_24h_had_only_other_sources(self):
        con = connect(self.db_path)
        now = int(time.time())
        five_days_ago = now - (5 * 86400)
        # 12 YoMovies titles from 5 days ago (within 3-month window)
        for i in range(12):
            self._seed_item(con, i, "yomovies", f"Recent Yo {i:02d}", year="2026", first_added_at=five_days_ago - i)
        # 15 ask4movie/movies7 titles from today's crawl
        for i in range(15):
            src = "ask4movie" if i % 2 == 0 else "movies7"
            self._seed_item(con, 300 + i, src, f"Today Crawl {i:02d}", year="2026", first_added_at=now - i)
        con.commit()
        con.close()

        resp = self.client.get("/api/catalog/recently-added?limit=30&window_months=3&latest_crawl=true")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["items"]
        self.assertEqual(len(items), 25)
        self.assertTrue(all(it["source"] == "yomovies" for it in items[:10]))
        self.assertTrue(all(it["source"] != "yomovies" for it in items[10:]))


if __name__ == "__main__":
    unittest.main()
