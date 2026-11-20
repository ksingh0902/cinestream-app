"""Focused backend tests for CINEMY Trending Now & Recommended for You discovery services."""
from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import shutil
import tempfile
import time
import unittest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.routes_discovery import router as discovery_router
from app.db.migrate import migrate_database
from app.discovery import invalidate_discovery_cache
from scraper.store import connect, upsert


SEED_CATALOG = [
    {
        "url": "https://ex.com/m/nolan-1",
        "title": "Interstellar",
        "year": "2024",
        "genres": ["Sci-fi", "Drama"],
        "actors": ["Matthew McConaughey", "Anne Hathaway"],
        "director": ["Christopher Nolan"],
        "language": "English",
        "quality": "4K",
        "rating": 8.7,
        "is_series": 0,
        "source": "yomovies",
        "source_id": "ym-interstellar",
        "poster": "https://ex.com/p/interstellar.jpg",
    },
    {
        "url": "https://ex.com/m/nolan-1-dup",
        "title": "Interstellar (2024) Hindi Dubbed",
        "year": "2024",
        "genres": ["Sci-fi", "Drama"],
        "actors": ["Matthew McConaughey"],
        "director": ["Christopher Nolan"],
        "language": "Hindi",
        "quality": "720p",
        "rating": 8.7,
        "is_series": 0,
        "source": "ask4movie",
        "source_id": "a4m-interstellar",
        "poster": "https://ex.com/p/interstellar2.jpg",
    },
    {
        "url": "https://ex.com/m/nolan-2",
        "title": "Inception",
        "year": "2025",
        "genres": ["Sci-fi", "Action"],
        "actors": ["Leonardo DiCaprio", "Anne Hathaway"],
        "director": ["Christopher Nolan"],
        "language": "English",
        "quality": "4K",
        "rating": 8.8,
        "is_series": 0,
        "source": "yomovies",
        "source_id": "ym-inception",
        "poster": "https://ex.com/p/inception.jpg",
    },
    {
        "url": "https://ex.com/m/nolan-3",
        "title": "Tenet",
        "year": "2025",
        "genres": ["Sci-fi", "Thriller"],
        "actors": ["John David Washington"],
        "director": ["Christopher Nolan"],
        "language": "English",
        "quality": "1080p",
        "rating": 7.5,
        "is_series": 0,
        "source": "yomovies",
        "source_id": "ym-tenet",
        "poster": "https://ex.com/p/tenet.jpg",
    },
    {
        "url": "https://ex.com/m/horror-1",
        "title": "The Conjuring",
        "year": "2025",
        "genres": ["Horror", "Mystery"],
        "actors": ["Vera Farmiga", "Patrick Wilson"],
        "director": ["James Wan"],
        "language": "English",
        "quality": "1080p",
        "rating": 7.6,
        "is_series": 0,
        "source": "yomovies",
        "source_id": "ym-conjuring",
        "poster": "https://ex.com/p/conjuring.jpg",
    },
    {
        "url": "https://ex.com/m/horror-2",
        "title": "Insidious",
        "year": "2026",
        "genres": ["Horror", "Thriller"],
        "actors": ["Patrick Wilson", "Rose Byrne"],
        "director": ["James Wan"],
        "language": "English",
        "quality": "1080p",
        "rating": 7.2,
        "is_series": 0,
        "source": "yomovies",
        "source_id": "ym-insidious",
        "poster": "https://ex.com/p/insidious.jpg",
    },
    {
        "url": "https://ex.com/m/horror-3",
        "title": "Malignant",
        "year": "2024",
        "genres": ["Horror", "Mystery"],
        "actors": ["Annabelle Wallis"],
        "director": ["James Wan"],
        "language": "English",
        "quality": "1080p",
        "rating": 6.8,
        "is_series": 0,
        "source": "yomovies",
        "source_id": "ym-malignant",
        "poster": "https://ex.com/p/malignant.jpg",
    },
    {
        "url": "https://ex.com/s/series-1",
        "title": "Dark Matter",
        "year": "2026",
        "genres": ["Sci-fi", "Drama"],
        "actors": ["Joel Edgerton"],
        "director": ["Jakob Verbruggen"],
        "language": "English",
        "quality": "4K",
        "rating": 8.1,
        "is_series": 1,
        "source": "yomovies",
        "source_id": "ym-darkmatter",
        "poster": "https://ex.com/p/darkmatter.jpg",
    },
    {
        "url": "https://ex.com/m/punjabi-1",
        "title": "Jatt & Juliet 3",
        "year": "2026",
        "genres": ["Comedy", "Punjabi"],
        "actors": ["Diljit Dosanjh"],
        "director": ["Jagdeep Sidhu"],
        "language": "Punjabi",
        "quality": "Punjabi",
        "rating": 7.9,
        "is_series": 0,
        "source": "yomovies",
        "source_id": "ym-jatt3",
        "poster": "https://ex.com/p/jatt3.jpg",
    },
    {
        "url": "https://ex.com/m/old-hit",
        "title": "Old Classic",
        "year": "2018",
        "genres": ["Drama"],
        "actors": ["Actor X"],
        "director": ["Director X"],
        "language": "English",
        "quality": "HD",
        "rating": 7.1,
        "is_series": 0,
        "source": "dooflix",
        "source_id": "df-old",
        "poster": "https://ex.com/p/old.jpg",
    },
]


class TestTrendingAndRecommendations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="cinemy_discovery_test_")
        cls.db_path = os.path.join(cls.temp_dir, "test_discovery.db")
        os.environ["DB_PATH"] = cls.db_path

        con = connect(cls.db_path)
        con.close()
        migrate_database(cls.db_path)

        con = connect(cls.db_path)
        cls.ids: dict[str, int] = {}
        for item in SEED_CATALOG:
            upsert(con, dict(item))
            con.execute(
                "UPDATE movies SET rating = ?, language = ?, source = ?, source_id = ? WHERE url = ?",
                (item.get("rating"), item.get("language"), item.get("source"), item.get("source_id"), item["url"]),
            )
            mid = con.execute("SELECT id FROM movies WHERE url = ?", (item["url"],)).fetchone()[0]
            cls.ids[item["source_id"]] = int(mid)
        con.commit()
        con.close()

        # Test FastAPI app with header-driven mock session middleware (simulates PrivateAccessMiddleware)
        cls.app = FastAPI()

        @cls.app.middleware("http")
        async def mock_auth_middleware(request: Request, call_next):
            test_user = request.headers.get("X-Test-User")
            if test_user:
                request.state.session = {"username": test_user, "role": "viewer"}
                request.state.user = {"username": test_user, "role": "viewer"}
            return await call_next(request)

        cls.app.include_router(discovery_router)
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls):
        invalidate_discovery_cache()
        if "DB_PATH" in os.environ:
            del os.environ["DB_PATH"]
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        invalidate_discovery_cache()
        # Reset optional viewer_activity table between tests
        con = connect(self.db_path)
        con.execute("DROP TABLE IF EXISTS viewer_activity")
        con.commit()
        con.close()

    # --- Trending Tests ---
    def test_01_trending_fallback_deterministic_deduped_and_bounded(self):
        r1 = self.client.get("/api/discovery/trending?limit=6")
        r2 = self.client.get("/api/discovery/trending?limit=6")
        self.assertEqual(r1.status_code, 200)
        d1, d2 = r1.json(), r2.json()
        self.assertEqual(d1["mode"], "fallback_trending")
        self.assertTrue(d1["is_fallback"])
        self.assertLessEqual(len(d1["items"]), 6)
        self.assertEqual([i["id"] for i in d1["items"]], [i["id"] for i in d2["items"]])

        # Interstellar has two mirrors (yomovies + ask4movie) -> must appear only once, preferring yomovies
        interstellar_hits = [i for i in d1["items"] if "interstellar" in i["title"].lower()]
        self.assertLessEqual(len(interstellar_hits), 1)
        if interstellar_hits:
            self.assertEqual(interstellar_hits[0]["source"], "yomovies")

    def test_02_trending_activity_weights_recent_and_unique_viewers(self):
        now = int(time.time())
        con = connect(self.db_path)
        con.execute("""
            CREATE TABLE viewer_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                viewer_id TEXT NOT NULL,
                movie_id INTEGER NOT NULL,
                watched_seconds REAL DEFAULT 0,
                duration_seconds REAL DEFAULT 0,
                created_at INTEGER NOT NULL
            )
        """)
        # Movie A (Jatt & Juliet 3): 4 distinct viewers watched recently with high completion
        for v in ("viewer:u1", "viewer:u2", "viewer:u3", "viewer:u4"):
            con.execute(
                "INSERT INTO viewer_activity (viewer_id, movie_id, watched_seconds, duration_seconds, created_at) VALUES (?, ?, ?, ?, ?)",
                (v, self.ids["ym-jatt3"], 6000, 6500, now - 3600),
            )
        # Movie B (Old Classic): 1 viewer looped it 10 times 10 days ago with low completion
        for i in range(10):
            con.execute(
                "INSERT INTO viewer_activity (viewer_id, movie_id, watched_seconds, duration_seconds, created_at) VALUES (?, ?, ?, ?, ?)",
                ("viewer:spammer", self.ids["df-old"], 30, 6000, now - 10 * 86400 + i),
            )
        # Add 2 more recent titles so activity mode threshold is met
        for sid in ("ym-inception", "ym-conjuring", "ym-darkmatter"):
            con.execute(
                "INSERT INTO viewer_activity (viewer_id, movie_id, watched_seconds, duration_seconds, created_at) VALUES (?, ?, ?, ?, ?)",
                ("viewer:u1", self.ids[sid], 3000, 3600, now - 7200),
            )
        con.commit()
        con.close()

        r = self.client.get("/api/discovery/trending?limit=5")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["mode"], "activity")
        self.assertFalse(data["is_fallback"])
        titles = [i["title"] for i in data["items"]]
        self.assertEqual(titles[0], "Jatt & Juliet 3")
        self.assertLess(titles.index("Jatt & Juliet 3"), titles.index("Old Classic"))

    def test_03_trending_rejects_invalid_limits(self):
        self.assertEqual(self.client.get("/api/discovery/trending?limit=0").status_code, 422)
        self.assertEqual(self.client.get("/api/discovery/trending?limit=999").status_code, 422)

    # --- Recommendation Tests ---
    def test_04_recommended_requires_auth_and_ignores_arbitrary_user_id(self):
        # Unauthenticated -> 401
        r_unauth = self.client.get("/api/discovery/recommended")
        self.assertEqual(r_unauth.status_code, 401)

        # Authenticated new user -> Evergreen Picks fallback (distinct from Trending)
        r_new = self.client.get(
            "/api/discovery/recommended?user_id=admin",
            headers={"X-Test-User": "brand_new_viewer"},
        )
        self.assertEqual(r_new.status_code, 200)
        data = r_new.json()
        self.assertFalse(data["personalized"])
        self.assertEqual(data["mode"], "evergreen_fallback")
        self.assertGreater(len(data["items"]), 0)

    def test_05_recommended_personalized_per_viewer_and_excludes_watched(self):
        now = int(time.time())
        con = connect(self.db_path)
        con.execute("""
            CREATE TABLE viewer_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                viewer_id TEXT NOT NULL,
                movie_id INTEGER NOT NULL,
                watched_seconds REAL DEFAULT 0,
                duration_seconds REAL DEFAULT 0,
                created_at INTEGER NOT NULL
            )
        """)
        # Viewer A watched Interstellar (Christopher Nolan / Sci-fi) to completion
        con.execute(
            "INSERT INTO viewer_activity (viewer_id, movie_id, watched_seconds, duration_seconds, created_at) VALUES (?, ?, ?, ?, ?)",
            ("viewer:alice", self.ids["ym-interstellar"], 9000, 9500, now - 1000),
        )
        # Viewer B watched The Conjuring (James Wan / Horror) to completion
        con.execute(
            "INSERT INTO viewer_activity (viewer_id, movie_id, watched_seconds, duration_seconds, created_at) VALUES (?, ?, ?, ?, ?)",
            ("viewer:bob", self.ids["ym-conjuring"], 6500, 6800, now - 1000),
        )
        con.commit()
        con.close()

        ra = self.client.get("/api/discovery/recommended?limit=6", headers={"X-Test-User": "alice"}).json()
        rb = self.client.get("/api/discovery/recommended?limit=6", headers={"X-Test-User": "bob"}).json()

        self.assertTrue(ra["personalized"])
        self.assertTrue(rb["personalized"])

        titles_a = [i["title"] for i in ra["items"]]
        titles_b = [i["title"] for i in rb["items"]]

        # Alice gets Nolan/Sci-fi (Inception #1) and NEVER gets already-watched Interstellar (nor its mirror)
        self.assertEqual(titles_a[0], "Inception")
        self.assertFalse(any("interstellar" in t.lower() for t in titles_a))

        # Bob gets James Wan/Horror (Insidious / Malignant) and NEVER gets already-watched The Conjuring
        self.assertIn(titles_b[0], ("Insidious", "Malignant"))
        self.assertNotIn("The Conjuring", titles_b)
        self.assertNotEqual(titles_a[0], titles_b[0])

    def test_06_recommended_ignores_device_local_seed_ids_for_cross_platform_consistency(self):
        """Option A: client-supplied seed_ids without server-side viewer_activity must fall back to Evergreen Picks."""
        seed_id = self.ids["ym-conjuring"]
        r_wap = self.client.get(
            f"/api/discovery/recommended?limit=5&seed_ids={seed_id}&exclude_ids={seed_id}",
            headers={"X-Test-User": "carol"},
        ).json()
        r_web = self.client.get(
            "/api/discovery/recommended?limit=5",
            headers={"X-Test-User": "carol"},
        ).json()

        self.assertFalse(r_wap["personalized"])
        self.assertFalse(r_web["personalized"])
        self.assertEqual(r_wap["mode"], "evergreen_fallback")
        self.assertEqual(r_web["mode"], "evergreen_fallback")
        self.assertGreater(len(r_wap["items"]), 0)
        self.assertGreater(len(r_web["items"]), 0)

    def test_07_trending_ranking_differs_from_evergreen_popular_ranking(self):
        """New Movie with high recent activity tops Trending; 2010 high-rated classic tops Popular."""
        now = int(time.time())
        con = connect(self.db_path)
        # Seed a 2010 evergreen classic (rating 9.2, rich cast/director) and a mediocre 2026 hype film (rating 6.4)
        classic_url = "https://ex.com/m/classic-2010"
        hype_url = "https://ex.com/m/hype-2026"
        upsert(con, {
            "url": classic_url,
            "title": "Evergreen Classic",
            "year": "2010",
            "genres": ["Drama", "Thriller", "Sci-fi"],
            "actors": ["Actor 1", "Actor 2", "Actor 3", "Actor 4", "Actor 5"],
            "director": ["Legendary Director"],
            "quality": "4K",
            "is_series": 0,
            "poster": "https://ex.com/p/classic.jpg",
            "synopsis": "An iconic evergreen masterpiece beloved by audiences for over a decade.",
        })
        con.execute("UPDATE movies SET rating = 9.2, source = 'yomovies', source_id = 'ym-classic-2010' WHERE url = ?", (classic_url,))
        classic_id = int(con.execute("SELECT id FROM movies WHERE url = ?", (classic_url,)).fetchone()[0])

        upsert(con, {
            "url": hype_url,
            "title": "New Hype 2026",
            "year": "2026",
            "genres": ["Action"],
            "actors": ["Actor H"],
            "director": ["Dir H"],
            "quality": "HD",
            "is_series": 0,
            "poster": "https://ex.com/p/hype.jpg",
            "synopsis": "A brand new release getting lots of clicks today.",
        })
        con.execute("UPDATE movies SET rating = 6.4, source = 'yomovies', source_id = 'ym-hype-2026' WHERE url = ?", (hype_url,))
        hype_id = int(con.execute("SELECT id FROM movies WHERE url = ?", (hype_url,)).fetchone()[0])

        con.execute("""
            CREATE TABLE viewer_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                viewer_id TEXT NOT NULL,
                movie_id INTEGER NOT NULL,
                watched_seconds REAL DEFAULT 0,
                duration_seconds REAL DEFAULT 0,
                created_at INTEGER NOT NULL
            )
        """)
        for v in ("viewer:v1", "viewer:v2", "viewer:v3", "viewer:v4", "viewer:v5"):
            con.execute(
                "INSERT INTO viewer_activity (viewer_id, movie_id, watched_seconds, duration_seconds, created_at) VALUES (?, ?, ?, ?, ?)",
                (v, hype_id, 5000, 6000, now - 1800),
            )
        for sid in ("ym-jatt3", "ym-conjuring", "ym-darkmatter"):
            con.execute(
                "INSERT INTO viewer_activity (viewer_id, movie_id, watched_seconds, duration_seconds, created_at) VALUES (?, ?, ?, ?, ?)",
                ("viewer:v1", self.ids[sid], 3000, 3600, now - 3600),
            )
        con.commit()
        con.close()
        invalidate_discovery_cache()

        trending = self.client.get("/api/discovery/trending?limit=4").json()
        popular = self.client.get("/api/discovery/popular?limit=4").json()

        self.assertEqual(trending["items"][0]["id"], hype_id)
        self.assertEqual(popular["items"][0]["id"], classic_id)
        self.assertNotEqual([i["id"] for i in trending["items"]], [i["id"] for i in popular["items"]])

        # Clean up extra test rows so other tests remain isolated
        con = connect(self.db_path)
        con.execute("DELETE FROM movies WHERE id IN (?, ?)", (classic_id, hype_id))
        con.commit()
        con.close()

    def test_08_popular_cross_row_exclusion_prevents_overlap_with_trending(self):
        trending = self.client.get("/api/discovery/trending?limit=4").json()
        trending_ids = [i["id"] for i in trending["items"]]
        ex_csv = ",".join(str(x) for x in trending_ids)

        popular = self.client.get(f"/api/discovery/popular?limit=4&exclude_ids={ex_csv}").json()
        popular_ids = [i["id"] for i in popular["items"]]

        overlap = set(trending_ids) & set(popular_ids)
        self.assertEqual(len(overlap), 0)

        # Also verify new viewer hitting /recommended automatically gets 0 overlap with Trending
        rec_new = self.client.get(
            "/api/discovery/recommended?limit=4",
            headers={"X-Test-User": "fresh_user_diversity"},
        ).json()
        self.assertEqual(rec_new["mode"], "evergreen_fallback")
        self.assertEqual(len(set(trending_ids) & {i["id"] for i in rec_new["items"]}), 0)

    def test_09_evergreen_excludes_animated_titles_and_supports_limit_50(self):
        """Animated titles are excluded from both Evergreen and Trending via catalogue metadata."""
        con = connect(self.db_path)
        anim_url = "https://ex.com/m/animated-95"
        upsert(con, {
            "url": anim_url,
            "title": "Top Rated Anime Film",
            "year": "2024",
            "genres": ["Animation", "Adventure", "Fantasy"],
            "actors": ["VA 1", "VA 2", "VA 3", "VA 4", "VA 5"],
            "director": ["Anime Director"],
            "quality": "4K",
            "is_series": 0,
            "poster": "https://ex.com/p/anime.jpg",
            "synopsis": "A critically acclaimed animated film that should not appear in Evergreen or Trending.",
        })
        con.execute("UPDATE movies SET rating = 9.4, source = 'yomovies', source_id = 'ym-anim-95' WHERE url = ?", (anim_url,))
        anim_id = int(con.execute("SELECT id FROM movies WHERE url = ?", (anim_url,)).fetchone()[0])
        con.commit()
        con.close()
        invalidate_discovery_cache()

        ev = self.client.get("/api/discovery/evergreen?limit=50")
        tr = self.client.get("/api/discovery/trending?limit=50")
        self.assertEqual(ev.status_code, 200)
        self.assertEqual(tr.status_code, 200)
        ev_data, tr_data = ev.json(), tr.json()
        self.assertEqual(ev_data["mode"], "evergreen_picks")
        self.assertLessEqual(len(ev_data["items"]), 50)
        self.assertLessEqual(len(tr_data["items"]), 50)
        self.assertNotIn(anim_id, [i["id"] for i in ev_data["items"]])
        self.assertNotIn(anim_id, [i["id"] for i in tr_data["items"]])

        # Verify >50 limit is rejected
        self.assertEqual(self.client.get("/api/discovery/evergreen?limit=51").status_code, 422)
        self.assertEqual(self.client.get("/api/discovery/trending?limit=51").status_code, 422)

        con = connect(self.db_path)
        con.execute("DELETE FROM movies WHERE id = ?", (anim_id,))
        con.commit()
        con.close()

    def test_10_evergreen_excludes_trending_by_canonical_identity_and_excludes_punjabi(self):
        """Excluding a Trending row ID also excludes its mirror row via canonical title, and Punjabi titles are excluded from Evergreen."""
        # Interstellar has yomovies (ym-interstellar) and ask4movie (a4m-interstellar) mirrors
        ex_id = self.ids["ym-interstellar"]
        ev = self.client.get(f"/api/discovery/evergreen?limit=7&exclude_ids={ex_id}").json()
        ev_titles = [i["title"].lower() for i in ev["items"]]

        # Neither Interstellar mirror should appear in Evergreen when enough other candidates exist
        self.assertFalse(any("interstellar" in t for t in ev_titles))
        # Punjabi titles (e.g. Jatt & Juliet 3) are excluded from Evergreen Picks
        self.assertFalse(any("jatt & juliet" in t for t in ev_titles))


if __name__ == "__main__":
    unittest.main()
