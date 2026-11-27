"""Focused unit tests for YoMovies re-publish detection, canonical matching, version replacement, and quality upgrades."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.catalogue.quality import (
    extract_print_quality,
    is_quality_downgrade,
    is_quality_upgrade,
    parse_quality_tier,
)
from app.db.migrate import migrate_database
from app.sync import (
    _should_recheck_yomovies_detail,
    upsert_yomovies_item,
)
from scraper.extract import parse_detail
from scraper.store import connect


def _make_item(
    *,
    url: str,
    title: str,
    year: str = "2026",
    quality: str = "HINDI",
    print_quality: str | None = None,
    embeds: list | None = None,
    downloads: list | None = None,
    is_series: int = 0,
    genres: list | None = None,
    tmdb_id: str | None = None,
    article_modified_time: str | None = None,
) -> dict:
    item = {
        "url": url,
        "title": title,
        "year": year,
        "quality": quality,
        "embeds": embeds if embeds is not None else [
            {"code": "abc123old", "host": "speedostream1.com", "url": "https://speedostream1.com/embed-abc123old.html", "type": "speedo"}
        ],
        "downloads": downloads if downloads is not None else [
            {"url": "https://speedostream1.com/abc123old.html", "server": "HD", "language": "Hindi"}
        ],
        "is_series": is_series,
        "genres": genres if genres is not None else ["Bollywood", "Action"],
        "poster": "https://ex.com/poster.jpg",
        "synopsis": "Test synopsis for YoMovies movie.",
        "tmdb_id": tmdb_id,
    }
    if print_quality is not None:
        item["print_quality"] = print_quality
    if article_modified_time is not None:
        item["article_modified_time"] = article_modified_time
    return item


class TestYoMoviesUpgradeAndRepublish(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cinemy_ym_upgrade_")
        self.db_path = os.path.join(self.temp_dir, "test_ym_upgrade.db")
        con = connect(self.db_path)
        con.close()
        migrate_database(self.db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _row_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0])

    def _get_row(self, movie_id: int) -> dict:
        return dict(self.conn.execute("SELECT * FROM movies WHERE id=?", (movie_id,)).fetchone())

    def test_01_new_movie_inserted_normally(self):
        status = {}
        item = _make_item(
            url="https://yomovies.irish/hanuman-ansh-2026-Watch-online-full-movie/",
            title="Hanuman Ansh (2026)",
            tmdb_id="991234",
        )
        is_new = upsert_yomovies_item(self.conn, item, updated_at=1700000100, status_out=status)
        self.assertTrue(is_new)
        self.assertEqual(status["outcome"], "inserted")
        self.assertEqual(self._row_count(), 1)

    def test_02_existing_same_url_same_embed_no_duplicate_and_unchanged(self):
        item = _make_item(
            url="https://yomovies.irish/hanuman-ansh-2026-Watch-online-full-movie/",
            title="Hanuman Ansh (2026)",
        )
        upsert_yomovies_item(self.conn, item, updated_at=1700000100)
        row1 = dict(self.conn.execute("SELECT * FROM movies").fetchone())

        status = {}
        is_new = upsert_yomovies_item(self.conn, item, updated_at=1700000500, status_out=status)
        self.assertFalse(is_new)
        self.assertEqual(status["outcome"], "unchanged")
        self.assertEqual(self._row_count(), 1)

        row2 = self._get_row(row1["id"])
        self.assertEqual(row2["first_added_at"], row1["first_added_at"])
        self.assertEqual(row2["last_updated_at"], row1["last_updated_at"])
        self.assertEqual(row2["embeds"], row1["embeds"])

    def test_03_same_movie_with_dash2_slug_updates_existing_canonical_row(self):
        orig = _make_item(
            url="https://yomovies.irish/hanuman-ansh-2026-Watch-online-full-movie/",
            title="Hanuman Ansh (2026)",
            tmdb_id="777111",
            genres=["Bollywood"],
        )
        upsert_yomovies_item(self.conn, orig, updated_at=1700000100)
        orig_row = dict(self.conn.execute("SELECT * FROM movies").fetchone())
        self.conn.execute("UPDATE movies SET first_added_at = 1690000000 WHERE id = ?", (orig_row["id"],))
        self.conn.commit()

        repost = _make_item(
            url="https://yomovies.irish/hanuman-ansh-2026-2-Watch-online-full-movie/",
            title="Hanuman Ansh (2026)",
            embeds=[{"code": "xyz999new", "host": "speedostream1.com", "url": "https://speedostream1.com/embed-xyz999new.html", "type": "speedo"}],
            genres=["Action"],
            tmdb_id=None,
        )
        status = {}
        is_new = upsert_yomovies_item(self.conn, repost, updated_at=1700000900, status_out=status)
        self.assertFalse(is_new)
        self.assertEqual(status["match_kind"], "canonical")
        self.assertEqual(status["outcome"], "playable_updated")
        self.assertEqual(self._row_count(), 1)

        updated = self._get_row(orig_row["id"])
        self.assertEqual(updated["id"], orig_row["id"])
        self.assertEqual(updated["first_added_at"], 1690000000)
        self.assertEqual(updated["tmdb_id"], 777111)
        self.assertIn("xyz999new", updated["embeds"])
        self.assertIn("Bollywood", json.loads(updated["genres"]))
        self.assertIn("Action", json.loads(updated["genres"]))

    def test_04_cam_or_cinema_to_hd_records_upgrade_and_preserves_first_added_at(self):
        cam = _make_item(
            url="https://yomovies.irish/hanuman-ansh-2026-Watch-online-full-movie/",
            title="Hanuman Ansh (2026) Cinema",
            quality="Cinema",
            embeds=[{"code": "cam111", "host": "speedostream1.com", "url": "https://speedostream1.com/embed-cam111.html", "type": "speedo"}],
        )
        upsert_yomovies_item(self.conn, cam, updated_at=1700000100)
        row1 = dict(self.conn.execute("SELECT * FROM movies").fetchone())
        self.conn.execute("UPDATE movies SET first_added_at = 1695000000 WHERE id = ?", (row1["id"],))
        self.conn.commit()

        hd = _make_item(
            url="https://yomovies.irish/hanuman-ansh-2026-2-Watch-online-full-movie/",
            title="Hanuman Ansh (2026) 1080p WEB-DL",
            quality="WEB-DL",
            embeds=[{"code": "hd222", "host": "speedostream1.com", "url": "https://speedostream1.com/embed-hd222.html", "type": "speedo"}],
            article_modified_time="2026-11-27T10:00:00+05:30",
        )
        status = {}
        is_new = upsert_yomovies_item(self.conn, hd, updated_at=1700009999, status_out=status)
        self.assertFalse(is_new)
        self.assertEqual(status["outcome"], "quality_upgraded")
        self.assertEqual(self._row_count(), 1)

        row2 = self._get_row(row1["id"])
        self.assertEqual(row2["first_added_at"], 1695000000)
        self.assertEqual(row2["best_quality"], "WEB-DL")
        self.assertEqual(row2["latest_quality_transition"], "Cinema → WEB-DL")
        self.assertIsNotNone(row2["last_quality_upgrade_at"])
        self.assertIn("hd222", row2["embeds"])

        hist = self.conn.execute("SELECT * FROM quality_history WHERE movie_id=?", (row1["id"],)).fetchall()
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["transition_badge"], "Cinema → WEB-DL")

    def test_05_hd_to_cam_does_not_downgrade(self):
        hd = _make_item(
            url="https://yomovies.irish/cool-movie-2026-Watch-online-full-movie/",
            title="Cool Movie (2026)",
            quality="1080p",
            embeds=[{"code": "goodhd1", "host": "speedostream1.com", "url": "https://speedostream1.com/embed-goodhd1.html", "type": "speedo"}],
        )
        upsert_yomovies_item(self.conn, hd, updated_at=1700000100)
        row1 = dict(self.conn.execute("SELECT * FROM movies").fetchone())

        cam = _make_item(
            url="https://yomovies.irish/cool-movie-2026-2-Watch-online-full-movie/",
            title="Cool Movie (2026) HDCAM",
            quality="HDCAM",
            embeds=[{"code": "badcam9", "host": "speedostream1.com", "url": "https://speedostream1.com/embed-badcam9.html", "type": "speedo"}],
        )
        status = {}
        upsert_yomovies_item(self.conn, cam, updated_at=1700000500, status_out=status)
        self.assertEqual(status["outcome"], "downgrade_ignored")
        self.assertEqual(self._row_count(), 1)

        row2 = self._get_row(row1["id"])
        self.assertEqual(row2["best_quality"], "1080p")
        self.assertIn("goodhd1", row2["embeds"])
        self.assertNotIn("badcam9", row2["embeds"])

    def test_06_unclear_quality_with_new_embed_updates_playable_without_fake_quality_upgrade(self):
        orig = _make_item(
            url="https://yomovies.irish/mystery-film-2026-Watch-online-full-movie/",
            title="Mystery Film (2026)",
            quality="HINDI",
            embeds=[{"code": "oldcode1", "host": "speedostream1.com", "url": "https://speedostream1.com/embed-oldcode1.html", "type": "speedo"}],
        )
        upsert_yomovies_item(self.conn, orig, updated_at=1700000100)
        row1 = dict(self.conn.execute("SELECT * FROM movies").fetchone())
        self.conn.execute("UPDATE movies SET first_added_at = 1690000000, resolved_at = 1699999999 WHERE id = ?", (row1["id"],))
        self.conn.commit()

        incoming = _make_item(
            url="https://yomovies.irish/mystery-film-2026-Watch-online-full-movie/",
            title="Mystery Film (2026)",
            quality="HINDI",
            embeds=[{"code": "newcode2", "host": "speedostream1.com", "url": "https://speedostream1.com/embed-newcode2.html", "type": "speedo"}],
        )
        status = {}
        upsert_yomovies_item(self.conn, incoming, updated_at=1700002000, status_out=status)
        self.assertEqual(status["outcome"], "playable_updated")

        row2 = self._get_row(row1["id"])
        self.assertIn("newcode2", row2["embeds"])
        self.assertIsNone(row2["resolved_at"])
        self.assertIsNone(row2["last_quality_upgrade_at"])
        self.assertIsNone(row2["latest_quality_transition"])
        self.assertEqual(row2["first_added_at"], 1690000000)
        self.assertEqual(row2["updated_at"], 1700002000)

    def test_07_different_year_never_merges(self):
        m2025 = _make_item(
            url="https://yomovies.irish/eclipse-2025-Watch-online-full-movie/",
            title="Eclipse (2025)",
            year="2025",
        )
        m2026 = _make_item(
            url="https://yomovies.irish/eclipse-2026-Watch-online-full-movie/",
            title="Eclipse (2026)",
            year="2026",
        )
        self.assertTrue(upsert_yomovies_item(self.conn, m2025, updated_at=1700000100))
        self.assertTrue(upsert_yomovies_item(self.conn, m2026, updated_at=1700000200))
        self.assertEqual(self._row_count(), 2)

    def test_08_different_sequel_or_part_never_merges(self):
        p1 = _make_item(
            url="https://yomovies.irish/hanuman-ansh-2026-Watch-online-full-movie/",
            title="Hanuman Ansh (2026)",
            year="2026",
        )
        p2 = _make_item(
            url="https://yomovies.irish/hanuman-ansh-part-2-2026-Watch-online-full-movie/",
            title="Hanuman Ansh Part 2 (2026)",
            year="2026",
        )
        seq2 = _make_item(
            url="https://yomovies.irish/hanuman-ansh-2-2026-Watch-online-full-movie/",
            title="Hanuman Ansh 2 (2026)",
            year="2026",
        )
        self.assertTrue(upsert_yomovies_item(self.conn, p1, updated_at=1700000100))
        self.assertTrue(upsert_yomovies_item(self.conn, p2, updated_at=1700000200))
        self.assertEqual(self._row_count(), 2)
        # Note: Part 2 and trailing "2" share sequel="2", while Part 1/base has sequel=""
        self.assertFalse(upsert_yomovies_item(self.conn, seq2, updated_at=1700000300))
        self.assertEqual(self._row_count(), 2)

    def test_09_different_series_season_never_merges(self):
        s1 = _make_item(
            url="https://yomovies.irish/dhindora-2026-season-1-Watch-online-full-movie/",
            title="Dhindora (2026) Season 1",
            year="2026",
            is_series=1,
        )
        s2 = _make_item(
            url="https://yomovies.irish/dhindora-2026-season-2-Watch-online-full-movie/",
            title="Dhindora (2026) Season 2",
            year="2026",
            is_series=1,
        )
        self.assertTrue(upsert_yomovies_item(self.conn, s1, updated_at=1700000100))
        self.assertTrue(upsert_yomovies_item(self.conn, s2, updated_at=1700000200))
        self.assertEqual(self._row_count(), 2)

    def test_10_language_is_not_quality_and_empty_embeds_preserve_existing(self):
        for lang in ("HINDI", "Punjabi", "Tamil", "Dual Audio", "English"):
            self.assertEqual(parse_quality_tier(lang), (None, None))
        self.assertEqual(is_quality_upgrade("HINDI", "HD"), (False, None))
        self.assertTrue(is_quality_downgrade("1080p", "Cinema"))
        self.assertEqual(extract_print_quality("HINDI", "Movie (2026) PreDVD"), "PreDVD")

        orig = _make_item(
            url="https://yomovies.irish/stable-film-2026-Watch-online-full-movie/",
            title="Stable Film (2026)",
            embeds=[{"code": "keepme1", "host": "speedostream1.com", "url": "https://speedostream1.com/embed-keepme1.html", "type": "speedo"}],
        )
        upsert_yomovies_item(self.conn, orig, updated_at=1700000100)
        row1 = dict(self.conn.execute("SELECT * FROM movies").fetchone())

        empty_inc = _make_item(
            url="https://yomovies.irish/stable-film-2026-Watch-online-full-movie/",
            title="Stable Film (2026)",
            embeds=[],
        )
        status = {}
        upsert_yomovies_item(self.conn, empty_inc, updated_at=1700000500, status_out=status)
        self.assertEqual(status["outcome"], "unchanged")
        row2 = self._get_row(row1["id"])
        self.assertIn("keepme1", row2["embeds"])

    def test_11_source_isolation_never_overwrites_other_sources(self):
        # Insert a Dooflix row with identical title & year
        self.conn.execute(
            """
            INSERT INTO movies (slug, url, title, year, quality, source, source_id, is_series, first_added_at, updated_at)
            VALUES ('doo-hanuman', 'https://dooflix.example/hanuman', 'Hanuman Ansh (2026)', '2026', '1080p', 'dooflix', 'doo-405', 0, 1690000000, 1690000000)
            """
        )
        self.conn.commit()

        ym = _make_item(
            url="https://yomovies.irish/hanuman-ansh-2026-Watch-online-full-movie/",
            title="Hanuman Ansh (2026)",
            year="2026",
        )
        self.assertTrue(upsert_yomovies_item(self.conn, ym, updated_at=1700000100))
        self.assertEqual(self._row_count(), 2)

    def test_12_parse_detail_extracts_dates_and_print_quality_and_bounded_recheck_policy(self):
        html = """
        <html>
          <head>
            <meta property="article:published_time" content="2026-10-01T08:00:00+00:00" />
            <meta property="article:modified_time" content="2026-11-27T09:15:00+00:00" />
            <script type="application/ld+json">
              {"@context":"https://schema.org","@graph":[{"@type":"WebPage","dateModified":"2026-11-27T09:15:00+00:00"}]}
            </script>
          </head>
          <body>
            <div class="mvic-desc"><h1>Hanuman Ansh (2026) WEB-DL</h1></div>
            <div class="mvic-info">
              <p><strong>Quality:</strong> HINDI</p>
              <p><strong>Release:</strong> <a href="/release-year/2026/">2026</a></p>
            </div>
            <iframe src="https://speedostream1.com/embed-newcode777.html"></iframe>
            <div id="list-dl"><a class="lnk-lnk" href="https://speedostream1.com/newcode777.html"><span class="serv_tit">HD</span><span class="lang_tit">Hindi</span></a></div>
          </body>
        </html>
        """
        parsed = parse_detail(html, "https://yomovies.irish/hanuman-ansh-2026-Watch-online-full-movie/")
        self.assertEqual(parsed["article_published_time"], "2026-10-01T08:00:00+00:00")
        self.assertEqual(parsed["article_modified_time"], "2026-11-27T09:15:00+00:00")
        self.assertEqual(parsed["jsonld_date_modified"], "2026-11-27T09:15:00+00:00")
        self.assertEqual(parsed["quality"], "HINDI")
        self.assertEqual(parsed["print_quality"], "WEB-DL")

        now_ts = int(time.time())
        recent_checked = {
            "title": "Hanuman Ansh (2026)",
            "quality": "HINDI",
            "embeds": '[{"code":"abc"}]',
            "first_added_at": now_ts - 5 * 86400,
            "last_checked_at": now_ts - 3600,  # checked 1 hour ago
        }
        # Recently checked same-URL row -> skip detail re-check
        self.assertFalse(
            _should_recheck_yomovies_detail(
                recent_checked,
                {"title": "Hanuman Ansh (2026)", "quality": "HINDI"},
                is_page_one_priority=True,
                is_canonical_repost=False,
                now_ts=now_ts,
            )
        )
        # Canonical '-2' repost -> ALWAYS re-check detail page
        self.assertTrue(
            _should_recheck_yomovies_detail(
                recent_checked,
                {"title": "Hanuman Ansh (2026)", "quality": "HINDI"},
                is_page_one_priority=False,
                is_canonical_repost=True,
                now_ts=now_ts,
            )
        )
        # Stale (>24h) recent movie on Page 1 -> re-check detail page
        stale_row = {**recent_checked, "last_checked_at": now_ts - 30 * 3600}
        self.assertTrue(
            _should_recheck_yomovies_detail(
                stale_row,
                {"title": "Hanuman Ansh (2026)", "quality": "HINDI"},
                is_page_one_priority=True,
                is_canonical_repost=False,
                now_ts=now_ts,
            )
        )


if __name__ == "__main__":
    unittest.main()
