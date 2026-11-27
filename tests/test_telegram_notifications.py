"""Unit tests for CINEMY Telegram notification service and SyncRunReport."""
from __future__ import annotations

import io
import logging
import os
import sys
import unittest
from unittest import mock

import requests

import app.sync as sync_mod
import sync_latest
from app.notifications import (
    OverallStatus,
    SourceRunReport,
    SourceStatus,
    SyncRunReport,
    TelegramConfig,
    TelegramNotifier,
    build_sync_run_report,
)


class _FakeTelegramResponse:
    def __init__(self, status_code: int, headers: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {}


class _ScriptedPostSession:
    def __init__(self, responses: list):
        self._responses = list(responses)
        self.posts: list[tuple[str, dict]] = []

    def post(self, url: str, json=None, timeout=None):
        del timeout
        self.posts.append((url, json or {}))
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    def close(self) -> None:
        pass


class TestTelegramNotifications(unittest.TestCase):
    def _sample_report(self, *, status: OverallStatus = OverallStatus.SUCCESS_WITH_WARNINGS) -> SyncRunReport:
        return SyncRunReport(
            run_id="sync-test-001",
            started_at=1795831200,
            finished_at=1795831422,
            duration_seconds=222.0,
            overall_status=status,
            sources=[
                SourceRunReport(source="Ask4Movies", status=SourceStatus.SUCCESS, discovered=1245, inserted=18, updated=37, duplicates=12, errors=0),
                SourceRunReport(source="Movies7", status=SourceStatus.SUCCESS, discovered=428, inserted=7, updated=12, duplicates=4, errors=0),
                SourceRunReport(source="DuoFlix", status=SourceStatus.SUCCESS, discovered=312, inserted=4, updated=8, duplicates=3, errors=0),
                SourceRunReport(source="FlixMovie", status=SourceStatus.SUCCESS, discovered=108, inserted=2, updated=15, duplicates=7, errors=0),
                SourceRunReport(source="YoMovies", status=SourceStatus.BLOCKED, http_status=403, blocked_reason="Cloudflare"),
                SourceRunReport(source="PRMovies", status=SourceStatus.BLOCKED, http_status=403, blocked_reason="Cloudflare"),
            ],
            warnings=["YoMovies HTTP 403", "PRMovies HTTP 403"],
        )

    def test_01_config_states_disabled_missing_token_missing_chat_and_enabled(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = TelegramConfig.from_env()
            ok, _ = cfg.is_ready()
            self.assertFalse(cfg.enabled)
            self.assertFalse(ok)

        with mock.patch.dict(os.environ, {"CINEMY_TELEGRAM_ENABLED": "true"}, clear=True):
            ok, reason = TelegramConfig.from_env().is_ready()
            self.assertFalse(ok)
            self.assertIn("BOT_TOKEN", reason)

        with mock.patch.dict(os.environ, {"CINEMY_TELEGRAM_ENABLED": "true", "CINEMY_TELEGRAM_BOT_TOKEN": "123:FAKE"}, clear=True):
            ok, reason = TelegramConfig.from_env().is_ready()
            self.assertFalse(ok)
            self.assertIn("CHAT_ID", reason)

        with mock.patch.dict(
            os.environ,
            {"CINEMY_TELEGRAM_ENABLED": "true", "CINEMY_TELEGRAM_BOT_TOKEN": "123:FAKE", "CINEMY_TELEGRAM_CHAT_ID": "99999"},
            clear=True,
        ):
            ok, reason = TelegramConfig.from_env().is_ready()
            self.assertTrue(ok)
            self.assertEqual(reason, "ready")

    def test_02_formatting_success_warnings_failed_zero_new_and_flixmovie(self):
        notifier = TelegramNotifier(TelegramConfig(enabled=False))

        # SUCCESS_WITH_WARNINGS with FlixMovie + blocked YoMovies/PRMovies
        text = notifier.format_sync_report(self._sample_report(status=OverallStatus.SUCCESS_WITH_WARNINGS))
        self.assertIn("CINEMY SYNC REPORT", text)
        self.assertIn("SUCCESS WITH WARNINGS", text)
        self.assertIn("FlixMovie", text)
        self.assertIn("YoMovies", text)
        self.assertIn("Status: BLOCKED", text)
        self.assertIn("HTTP: 403", text)
        self.assertIn("Total new: +31", text)
        self.assertIn("Total updated: 72", text)

        # Clean SUCCESS with zero new titles
        zero_rep = build_sync_run_report(
            [SourceRunReport(source="FlixMovie", status=SourceStatus.SUCCESS, discovered=50, inserted=0, updated=50)],
            started_at=1795831200,
            finished_at=1795831215,
        )
        text_ok = notifier.format_sync_report(zero_rep)
        self.assertIn("🟢 SUCCESS", text_ok)
        self.assertIn("Total new: +0", text_ok)
        self.assertIn("Completed cleanly", text_ok)

        # FAILED report
        fail_rep = build_sync_run_report(
            [SourceRunReport(source="Ask4Movies", status=SourceStatus.FAILED, http_status=500, errors=1)],
            started_at=1795831200,
            finished_at=1795831205,
            fatal_error="Database lock timeout",
        )
        text_fail = notifier.format_sync_report(fail_rep)
        self.assertIn("🔴 FAILED", text_fail)
        self.assertIn("Database lock timeout", text_fail)

    def test_03_secret_safety_token_never_leaks_in_report_exception_or_logs(self):
        secret_token = "987654321:SUPER_SECRET_BOT_TOKEN_XYZ"
        cfg = TelegramConfig(enabled=True, bot_token=secret_token, chat_id="12345", max_retries=0)
        # Simulate requests exception containing full URL with secret token
        sess = _ScriptedPostSession([
            requests.ConnectionError(f"HTTPSConnectionPool failed for https://api.telegram.org/bot{secret_token}/sendMessage")
        ])
        notifier = TelegramNotifier(cfg, session=sess, sleep_fn=lambda _: None)

        rep = self._sample_report()
        formatted = notifier.format_sync_report(rep)
        self.assertNotIn(secret_token, formatted)

        with self.assertLogs("cinemymovies.notifications.telegram", level="WARNING") as log_cm:
            res = notifier.send_sync_report(rep)

        self.assertFalse(res.sent)
        self.assertNotIn(secret_token, res.reason)
        for err in res.errors:
            self.assertNotIn(secret_token, err)
        for line in log_cm.output:
            self.assertNotIn(secret_token, line)

    def test_04_failure_isolation_http_500_429_timeout_never_fail_crawler(self):
        cfg = TelegramConfig(enabled=True, bot_token="111:TEST", chat_id="222", max_retries=1)
        rep = self._sample_report()

        # HTTP 500
        s500 = _ScriptedPostSession([_FakeTelegramResponse(500), _FakeTelegramResponse(500)])
        r500 = TelegramNotifier(cfg, session=s500, sleep_fn=lambda _: None).send_sync_report(rep)
        self.assertFalse(r500.sent)
        self.assertEqual(r500.http_status, 500)

        # HTTP 429 with Retry-After -> succeeds on retry
        sleeps: list[float] = []
        s429 = _ScriptedPostSession([_FakeTelegramResponse(429, headers={"Retry-After": "4"}), _FakeTelegramResponse(200)])
        r429 = TelegramNotifier(cfg, session=s429, sleep_fn=sleeps.append).send_sync_report(rep)
        self.assertTrue(r429.sent)
        self.assertEqual(sleeps, [4.0])

        # Timeout
        sto = _ScriptedPostSession([requests.Timeout("timed out"), requests.Timeout("timed out")])
        rto = TelegramNotifier(cfg, session=sto, sleep_fn=lambda _: None).send_sync_report(rep)
        self.assertFalse(rto.sent)

        # End-to-end: run_full_sync still returns status='success' even when TelegramNotifier explodes!
        broken_notifier = mock.MagicMock()
        broken_notifier.send_sync_report.side_effect = RuntimeError("telegram exploded")
        with (
            mock.patch.object(sync_mod, "sync_yomovies", return_value={"added": 0, "updated": 0, "total": 0}),
            mock.patch.object(sync_mod, "sync_moviesdrive", return_value={"added": 0, "updated": 0, "skipped": 0, "total": 0}),
            mock.patch.object(sync_mod, "sync_ask4movie", return_value={"added": 1, "updated": 2, "total": 3}),
            mock.patch.object(sync_mod, "sync_movies7", return_value={"added": 0, "updated": 1, "skipped": 0, "total": 1}),
            mock.patch.object(sync_mod, "sync_dooflix", return_value={"added": 0, "updated": 0, "skipped": 0, "total": 10}),
            mock.patch.object(sync_mod, "sync_flixmovie", return_value={"added": 2, "updated": 3, "skipped": 1, "total": 6}),
        ):
            summary = sync_mod.run_full_sync(notifier=broken_notifier)
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["total_added"], 3)
        broken_notifier.send_sync_report.assert_called_once()  # Exactly ONE notification per run

    def test_05_message_splitting_preserves_all_sources_without_truncation(self):
        sources = [
            SourceRunReport(
                source=f"Source_{i:02d}",
                status=SourceStatus.SUCCESS,
                discovered=100 + i,
                inserted=i,
                updated=i * 2,
                duplicates=1,
                errors=0,
            )
            for i in range(1, 26)
        ]
        big_report = build_sync_run_report(
            sources,
            started_at=1795831200,
            finished_at=1795831500,
        )
        big_report.warnings = [f"Warning item {i}" for i in range(1, 8)]

        notifier = TelegramNotifier(TelegramConfig(enabled=False), max_message_length=700)
        chunks = notifier.split_report_messages(big_report)
        self.assertGreater(len(chunks), 2)
        for ch in chunks:
            self.assertLessEqual(len(ch), 700)

        joined = "\n".join(chunks)
        self.assertIn("CINEMY SYNC SUMMARY", chunks[0])
        for i in range(1, 26):
            self.assertIn(f"Source_{i:02d}", joined)
        self.assertIn("WARNINGS / ERRORS", chunks[-1])

    def test_06_cli_test_telegram_disabled_makes_zero_http_and_zero_crawler_calls(self):
        buf = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"CINEMY_TELEGRAM_ENABLED": "false"}, clear=True),
            mock.patch.object(sys, "argv", ["sync_latest.py", "--test-telegram"]),
            mock.patch("sys.stdout", buf),
            mock.patch.object(sync_latest, "run_full_sync") as mock_full,
            mock.patch.object(sync_latest, "sync_yomovies") as mock_ym,
            mock.patch("requests.Session.post") as mock_post,
        ):
            sync_latest.main()

        out = buf.getvalue()
        self.assertIn("TELEGRAM TEST MODE", out)
        self.assertIn("CINEMY SYNC REPORT", out)
        self.assertIn("MoviesDrive", out)
        self.assertIn("FlixMovie", out)
        self.assertIn("Catalogue total: 16,353", out)
        self.assertIn("no message sent", out.lower())
        mock_full.assert_not_called()
        mock_ym.assert_not_called()
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
