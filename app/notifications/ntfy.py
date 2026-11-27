"""Isolated ntfy push notification service for CINEMY sync reports.

Safety guarantees:
- Configuration comes exclusively from environment variables (never hardcoded, never stored in SQLite).
- Disabled by default (CINEMY_NTFY_ENABLED=false) so local runs never push unexpectedly.
- Topic name and optional Bearer token are redacted from all logs and error messages.
- Best-effort delivery: ntfy HTTP/network/429/5xx failures NEVER fail the crawler.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

import requests

from .models import OverallStatus, SyncRunReport
from .telegram import TelegramConfig, TelegramNotifier

logger = logging.getLogger("cinemymovies.notifications.ntfy")

DEFAULT_NTFY_SERVER = "https://ntfy.sh"
NTFY_SAFE_MAX_LENGTH = 3800


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _redact(text: str, *secrets: str) -> str:
    out = str(text or "")
    for secret in secrets:
        if secret:
            out = out.replace(secret, "<REDACTED>")
    return out


@dataclass(frozen=True)
class NtfyConfig:
    enabled: bool = False
    topic: str = ""
    server: str = DEFAULT_NTFY_SERVER
    token: str = ""
    timeout_seconds: float = 10.0
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> "NtfyConfig":
        try:
            timeout = float(os.getenv("CINEMY_NTFY_TIMEOUT_SECONDS", "10"))
        except ValueError:
            timeout = 10.0
        try:
            retries = int(os.getenv("CINEMY_NTFY_MAX_RETRIES", "2"))
        except ValueError:
            retries = 2
        server = (os.getenv("CINEMY_NTFY_SERVER") or DEFAULT_NTFY_SERVER).strip().rstrip("/")
        return cls(
            enabled=_env_bool("CINEMY_NTFY_ENABLED", default=False),
            topic=(os.getenv("CINEMY_NTFY_TOPIC") or "").strip().strip("/"),
            server=server or DEFAULT_NTFY_SERVER,
            token=(os.getenv("CINEMY_NTFY_TOKEN") or "").strip(),
            timeout_seconds=max(1.0, timeout),
            max_retries=max(0, retries),
        )

    def is_ready(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "ntfy notifications disabled (CINEMY_NTFY_ENABLED is not true)"
        if not self.topic:
            return False, "CINEMY_NTFY_TOPIC is missing"
        return True, "ready"


@dataclass
class NtfySendResult:
    sent: bool = False
    skipped: bool = False
    messages_sent: int = 0
    http_status: Optional[int] = None
    reason: str = ""
    errors: List[str] = field(default_factory=list)


class NtfyNotifier:
    """Best-effort ntfy push notifier reusing SyncRunReport formatting."""

    def __init__(
        self,
        config: Optional[NtfyConfig] = None,
        *,
        session: Optional[Any] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        max_message_length: int = NTFY_SAFE_MAX_LENGTH,
    ) -> None:
        self.config = config if config is not None else NtfyConfig.from_env()
        self._session = session if session is not None else requests.Session()
        self._owns_session = session is None
        self._sleep = sleep_fn
        self._formatter = TelegramNotifier(TelegramConfig(enabled=False), max_message_length=max_message_length)

    @classmethod
    def from_env(cls) -> "NtfyNotifier":
        return cls(NtfyConfig.from_env())

    def format_sync_report(self, report: SyncRunReport) -> str:
        return self._formatter.format_sync_report(report)

    def split_report_messages(self, report: SyncRunReport) -> List[str]:
        return self._formatter.split_report_messages(report)

    def _title_for_report(self, report: SyncRunReport) -> str:
        if report.overall_status == OverallStatus.SUCCESS:
            return f"CINEMY Sync: SUCCESS (+{report.total_new} new)"
        if report.overall_status == OverallStatus.SUCCESS_WITH_WARNINGS:
            return f"CINEMY Sync: WARNINGS (+{report.total_new} new)"
        return "CINEMY Sync: FAILED"

    def _tags_and_priority(self, report: SyncRunReport) -> tuple[str, str]:
        if report.overall_status == OverallStatus.SUCCESS:
            return "clapper,white_check_mark", "default"
        if report.overall_status == OverallStatus.SUCCESS_WITH_WARNINGS:
            return "clapper,warning", "default"
        return "rotating_light", "high"

    def send_message(
        self,
        text: str,
        *,
        title: str = "CINEMY Sync Report",
        tags: str = "clapper",
        priority: str = "default",
    ) -> NtfySendResult:
        ready, reason = self.config.is_ready()
        if not ready:
            return NtfySendResult(sent=False, skipped=True, reason=reason)

        endpoint = f"{self.config.server}/{self.config.topic}"
        headers = {
            "Title": title,
            "Priority": priority,
            "Tags": tags,
            "Content-Type": "text/plain; charset=utf-8",
        }
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"

        last_status: Optional[int] = None
        last_err = ""
        for attempt in range(self.config.max_retries + 1):
            try:
                resp = self._session.post(
                    endpoint,
                    data=text.encode("utf-8"),
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                )
                last_status = int(getattr(resp, "status_code", 0) or 0)
                if 200 <= last_status < 300:
                    return NtfySendResult(sent=True, messages_sent=1, http_status=last_status, reason="ok")

                if last_status == 429:
                    retry_after = str(getattr(resp, "headers", {}).get("Retry-After", "") or "")
                    wait_secs = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 2.0
                    last_err = f"ntfy notification failed: HTTP 429 retry-after={retry_after or 'none'}"
                    if attempt < self.config.max_retries:
                        self._sleep(min(wait_secs, 30.0))
                        continue
                    logger.warning("%s", last_err)
                    return NtfySendResult(sent=False, http_status=429, reason=last_err, errors=[last_err])

                if last_status >= 500:
                    last_err = f"ntfy notification failed: HTTP {last_status}"
                    if attempt < self.config.max_retries:
                        self._sleep(min(1.5 * (attempt + 1), 10.0))
                        continue
                    logger.warning("%s", last_err)
                    return NtfySendResult(sent=False, http_status=last_status, reason=last_err, errors=[last_err])

                last_err = f"ntfy notification failed: HTTP {last_status}"
                logger.warning("%s", last_err)
                return NtfySendResult(sent=False, http_status=last_status, reason=last_err, errors=[last_err])
            except Exception as exc:
                safe_exc = _redact(f"{type(exc).__name__}: {exc}", self.config.topic, self.config.token)
                last_err = f"ntfy notification failed: {safe_exc}"
                if attempt < self.config.max_retries:
                    self._sleep(min(1.5 * (attempt + 1), 10.0))
                    continue
                logger.warning("%s", last_err)
                return NtfySendResult(sent=False, http_status=last_status, reason=last_err, errors=[last_err])

        return NtfySendResult(sent=False, http_status=last_status, reason=last_err, errors=[last_err])

    def send_sync_report(self, report: SyncRunReport) -> NtfySendResult:
        """Best-effort send of a SyncRunReport via ntfy. Guaranteed never to raise."""
        try:
            ready, reason = self.config.is_ready()
            if not ready:
                return NtfySendResult(sent=False, skipped=True, reason=reason)

            chunks = self.split_report_messages(report)
            title = self._title_for_report(report)
            tags, priority = self._tags_and_priority(report)
            sent_count = 0
            errors: List[str] = []
            last_status: Optional[int] = None
            for idx, chunk in enumerate(chunks, start=1):
                part_title = f"{title} ({idx}/{len(chunks)})" if len(chunks) > 1 else title
                res = self.send_message(chunk, title=part_title, tags=tags, priority=priority)
                last_status = res.http_status
                if res.sent:
                    sent_count += 1
                else:
                    errors.extend(res.errors or [res.reason])
                    break
            return NtfySendResult(
                sent=(sent_count == len(chunks) and sent_count > 0),
                messages_sent=sent_count,
                http_status=last_status,
                reason="ok" if sent_count == len(chunks) else (errors[0] if errors else "failed"),
                errors=errors,
            )
        except Exception as exc:
            safe_exc = _redact(f"{type(exc).__name__}: {exc}", self.config.topic, self.config.token)
            logger.warning("ntfy send_sync_report suppressed error: %s", safe_exc)
            return NtfySendResult(sent=False, reason=safe_exc, errors=[safe_exc])
        finally:
            if self._owns_session and self._session is not None:
                try:
                    self._session.close()
                except Exception:
                    pass
