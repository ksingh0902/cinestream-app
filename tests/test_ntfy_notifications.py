"""Unit tests for ntfy push notification service."""
from __future__ import annotations

import io
import os
import sys
import unittest
from unittest import mock

import requests

import sync_latest
from app.notifications import (
    NtfyConfig,
    NtfyNotifier,
    OverallStatus,
    SourceRunReport,
    SourceStatus,
    SyncRunReport,
)


class _FakeResp:
    def __init__(self, status_code: int, headers: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {}


class _ScriptedPostSession:
    def __init__(self, responses: list):
        self._responses = list(responses)
        self.posts: list[tuple[str, bytes, dict]] = []

    def post(self, url: str, data=None, headers=None, timeout=None):
        del timeout
        self.posts.append((url, data or b"", dict(headers or {})))
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    def close(self) -> None:
        pass


class TestNtfyNotifications(unittest.TestCase):
    def _sample(self) -> SyncRunReport:
        return SyncRunReport(
            run_id="ntfy-test-1",
            started_at=1795831200,
            finished_at=1795831320,
            duration_seconds=120.0,
            overall_status=OverallStatus.SUCCESS_WITH_WARNINGS,
            sources=[
                SourceRunReport(source="MoviesDrive", status=SourceStatus.SUCCESS, discovered=72, inserted=4, updated=12, duplicates=2),
                SourceRunReport(source="FlixMovie", status=SourceStatus.SUCCESS, discovered=108, inserted=2, updated=8, duplicates=3),
                SourceRunReport(source="YoMovies", status=SourceStatus.BLOCKED, http_status=403, blocked_reason="Cloudflare"),
            ],
            warnings=["YoMovies HTTP 403"],
            catalogue_total=16353,
        )

    def test_01_config_and_send_and_secret_redaction(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            ok, _ = NtfyConfig.from_env().is_ready()
            self.assertFalse(ok)

        secret_topic = "cinemy-private-topic-998877"
        cfg = NtfyConfig(enabled=True, topic=secret_topic, max_retries=0)
        sess_ok = _ScriptedPostSession([_FakeResp(200)])
        res = NtfyNotifier(cfg, session=sess_ok, sleep_fn=lambda _: None).send_sync_report(self._sample())
        self.assertTrue(res.sent)
        self.assertEqual(res.messages_sent, 1)
        self.assertEqual(sess_ok.posts[0][0], f"https://ntfy.sh/{secret_topic}")
        self.assertIn("CINEMY Sync: WARNINGS (+6 new)", sess_ok.posts[0][2]["Title"])

        # Failure redacts topic from error/logs and never raises
        sess_err = _ScriptedPostSession([requests.ConnectionError(f"failed https://ntfy.sh/{secret_topic}")])
        with self.assertLogs("cinemymovies.notifications.ntfy", level="WARNING") as log_cm:
            res_err = NtfyNotifier(cfg, session=sess_err, sleep_fn=lambda _: None).send_sync_report(self._sample())
        self.assertFalse(res_err.sent)
        self.assertNotIn(secret_topic, res_err.reason)
        for line in log_cm.output:
            self.assertNotIn(secret_topic, line)

    def test_02_cli_test_ntfy_disabled_by_default(self):
        buf = io.StringIO()
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(sys, "argv", ["sync_latest.py", "--test-ntfy"]),
            mock.patch("sys.stdout", buf),
            mock.patch("requests.Session.post") as mock_post,
        ):
            sync_latest.main()
        out = buf.getvalue()
        self.assertIn("NTFY TEST MODE", out)
        self.assertIn("MoviesDrive", out)
        self.assertIn("FlixMovie", out)
        self.assertIn("Catalogue total: 16,353", out)
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
