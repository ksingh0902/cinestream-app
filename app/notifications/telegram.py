"""Isolated Telegram Bot API notification service for CINEMY sync reports.

Safety guarantees:
- Configuration comes exclusively from environment variables (never hardcoded, never stored in SQLite).
- Disabled by default (CINEMY_TELEGRAM_ENABLED=false) so local developer runs never spam Telegram.
- Bot token is scrubbed from all logs, error messages, and exceptions.
- Best-effort delivery: Telegram HTTP/network/429/5xx failures NEVER fail the crawler.
- Automatic safe message splitting under Telegram's 4096-char limit without breaking mid-source.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List, Optional

import requests

from .models import OverallStatus, SourceRunReport, SourceStatus, SyncRunReport

logger = logging.getLogger("cinemymovies.notifications.telegram")

TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_SAFE_MAX_LENGTH = 3800  # Safely below Telegram's 4096-character hard limit
_IST = timezone(timedelta(hours=5, minutes=30))


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _redact_token(text: str, token: str) -> str:
    if not text or not token:
        return text or ""
    return str(text).replace(token, "<REDACTED_TOKEN>")


def _format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    mins, secs = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours}h {mins}m {secs}s"
    if mins > 0:
        return f"{mins}m {secs}s"
    return f"{secs}s"


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    timeout_seconds: float = 10.0
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> "TelegramConfig":
        try:
            timeout = float(os.getenv("CINEMY_TELEGRAM_TIMEOUT_SECONDS", "10"))
        except ValueError:
            timeout = 10.0
        try:
            retries = int(os.getenv("CINEMY_TELEGRAM_MAX_RETRIES", "2"))
        except ValueError:
            retries = 2
        return cls(
            enabled=_env_bool("CINEMY_TELEGRAM_ENABLED", default=False),
            bot_token=(os.getenv("CINEMY_TELEGRAM_BOT_TOKEN") or "").strip(),
            chat_id=(os.getenv("CINEMY_TELEGRAM_CHAT_ID") or "").strip(),
            timeout_seconds=max(1.0, timeout),
            max_retries=max(0, retries),
        )

    def is_ready(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "Telegram notifications disabled (CINEMY_TELEGRAM_ENABLED is not true)"
        if not self.bot_token:
            return False, "CINEMY_TELEGRAM_BOT_TOKEN is missing"
        if not self.chat_id:
            return False, "CINEMY_TELEGRAM_CHAT_ID is missing"
        return True, "ready"


@dataclass
class TelegramSendResult:
    sent: bool = False
    skipped: bool = False
    messages_sent: int = 0
    http_status: Optional[int] = None
    reason: str = ""
    errors: List[str] = field(default_factory=list)


def _status_badge(status: OverallStatus) -> str:
    if status == OverallStatus.SUCCESS:
        return "🟢 SUCCESS"
    if status == OverallStatus.SUCCESS_WITH_WARNINGS:
        return "🟡 SUCCESS WITH WARNINGS"
    return "🔴 FAILED"


def _source_badge(status: SourceStatus) -> str:
    if status == SourceStatus.SUCCESS:
        return "🟢"
    if status == SourceStatus.WARNING:
        return "🟡"
    return "🔴"


def _format_source_block(src: SourceRunReport) -> str:
    badge = _source_badge(src.status)
    lines = [f"{badge} {src.source}"]
    if src.status == SourceStatus.BLOCKED:
        lines.append("   Status: BLOCKED")
        if src.http_status is not None:
            lines.append(f"   HTTP: {src.http_status}")
        if src.blocked_reason:
            lines.append(f"   Reason: {src.blocked_reason}")
        return "\n".join(lines)

    if src.status == SourceStatus.FAILED:
        lines.append("   Status: FAILED")
        if src.http_status is not None:
            lines.append(f"   HTTP: {src.http_status}")
        lines.append(f"   Errors: {src.errors}")
        return "\n".join(lines)

    if src.discovered is not None:
        lines.append(f"   Discovered: {src.discovered}")
    lines.append(f"   New: +{src.inserted}")
    lines.append(f"   Updated: {src.updated}")
    if src.duplicates or src.skipped:
        lines.append(f"   Duplicates: {src.duplicates or src.skipped}")
    if src.quality_upgrades is not None and src.quality_upgrades > 0:
        lines.append(f"   Quality upgrades: {src.quality_upgrades}")
    if src.quality_downgrades is not None and src.quality_downgrades > 0:
        lines.append(f"   Downgrades blocked: {src.quality_downgrades}")
    if src.metadata_enriched is not None:
        lines.append(f"   Enriched: {src.metadata_enriched}")
    if src.http_status is not None and src.http_status != 200:
        lines.append(f"   HTTP: {src.http_status}")
    lines.append(f"   Errors: {src.errors}")
    return "\n".join(lines)


class TelegramNotifier:
    """Best-effort Telegram Bot API notifier for CINEMY sync reports."""

    def __init__(
        self,
        config: Optional[TelegramConfig] = None,
        *,
        session: Optional[Any] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        max_message_length: int = TELEGRAM_SAFE_MAX_LENGTH,
    ) -> None:
        self.config = config if config is not None else TelegramConfig.from_env()
        self._session = session if session is not None else requests.Session()
        self._owns_session = session is None
        self._sleep = sleep_fn
        self.max_message_length = max(256, min(int(max_message_length), 4096))

    @classmethod
    def from_env(cls) -> "TelegramNotifier":
        return cls(TelegramConfig.from_env())

    def format_sync_report(self, report: SyncRunReport) -> str:
        """Render a complete, phone-readable Telegram sync report."""
        dt_ist = datetime.fromtimestamp(report.finished_at or report.started_at, tz=_IST)
        date_str = dt_ist.strftime("%d %b %Y")
        time_str = dt_ist.strftime("%H:%M IST")

        lines = [
            "🎬 CINEMY SYNC REPORT",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            _status_badge(report.overall_status),
            f"📅 {date_str}",
            f"🕐 {time_str}",
            f"⏱ Duration: {_format_duration(report.duration_seconds)}",
            "",
            "SOURCES",
            "━━━━━━━━━━━━━━━━━━━━",
        ]

        if report.sources:
            for src in report.sources:
                lines.append("")
                lines.append(_format_source_block(src))
        else:
            lines.append("")
            lines.append("No sources recorded.")

        lines.extend(
            [
                "",
                "DATABASE",
                "━━━━━━━━━━━━━━━━━━━━",
                f"Total new: +{report.total_new}",
                f"Total updated: {report.total_updated}",
            ]
        )
        if report.total_quality_upgrades is not None:
            lines.append(f"Quality upgrades: {report.total_quality_upgrades}")
        lines.append(f"Duplicates prevented: {report.total_duplicates}")
        if report.catalogue_total is not None:
            lines.append(f"Catalogue total: {report.catalogue_total:,}")

        if report.warnings or report.error_summary:
            lines.extend(["", "WARNINGS", "━━━━━━━━━━━━━━━━━━━━"])
            if report.error_summary:
                lines.append(f"• {report.error_summary}")
            for w in report.warnings:
                lines.append(f"• {w}")

        lines.append("")
        if report.overall_status == OverallStatus.SUCCESS:
            lines.append("🟢 Completed cleanly")
        elif report.overall_status == OverallStatus.SUCCESS_WITH_WARNINGS:
            lines.append("🟡 Completed with warnings")
        else:
            lines.append("🔴 Sync failed")

        return _redact_token("\n".join(lines), self.config.bot_token)

    def split_report_messages(self, report: SyncRunReport) -> List[str]:
        """Return one message if within Telegram limits, else split cleanly at section/source boundaries."""
        full = self.format_sync_report(report)
        if len(full) <= self.max_message_length:
            return [full]

        dt_ist = datetime.fromtimestamp(report.finished_at or report.started_at, tz=_IST)
        summary_lines = [
            "🎬 CINEMY SYNC SUMMARY",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            _status_badge(report.overall_status),
            f"📅 {dt_ist.strftime('%d %b %Y')} | 🕐 {dt_ist.strftime('%H:%M IST')}",
            f"⏱ Duration: {_format_duration(report.duration_seconds)}",
            f"Sources: {len(report.sources)}",
            "",
            "DATABASE",
            "━━━━━━━━━━━━━━━━━━━━",
            f"Total new: +{report.total_new}",
            f"Total updated: {report.total_updated}",
        ]
        if report.total_quality_upgrades is not None:
            summary_lines.append(f"Quality upgrades: {report.total_quality_upgrades}")
        summary_lines.append(f"Duplicates prevented: {report.total_duplicates}")
        if report.catalogue_total is not None:
            summary_lines.append(f"Catalogue total: {report.catalogue_total:,}")

        messages: List[str] = [_redact_token("\n".join(summary_lines), self.config.bot_token)]

        # Pack whole source blocks without ever splitting inside a source block
        if report.sources:
            header = "📊 SOURCE DETAILS\n━━━━━━━━━━━━━━━━━━━━"
            cur = header
            for src in report.sources:
                block = _redact_token(_format_source_block(src), self.config.bot_token)
                candidate = f"{cur}\n\n{block}"
                if len(candidate) <= self.max_message_length:
                    cur = candidate
                else:
                    if cur != header:
                        messages.append(cur)
                    cur = f"{header}\n\n{block}"
            if cur != header:
                messages.append(cur)

        # Warnings/Errors message
        if report.warnings or report.error_summary:
            w_header = "⚠️ WARNINGS / ERRORS\n━━━━━━━━━━━━━━━━━━━━"
            cur = w_header
            all_w = ([report.error_summary] if report.error_summary else []) + list(report.warnings)
            for w in all_w:
                line = f"• {_redact_token(str(w), self.config.bot_token)}"
                candidate = f"{cur}\n{line}"
                if len(candidate) <= self.max_message_length:
                    cur = candidate
                else:
                    if cur != w_header:
                        messages.append(cur)
                    cur = f"{w_header}\n{line}"
            if cur != w_header:
                messages.append(cur)

        return messages

    def send_message(self, text: str) -> TelegramSendResult:
        """Send one message via Telegram's official Bot API with bounded retries and token redaction."""
        ready, reason = self.config.is_ready()
        if not ready:
            return TelegramSendResult(sent=False, skipped=True, reason=reason)

        safe_text = _redact_token(text, self.config.bot_token)
        endpoint = f"{TELEGRAM_API_BASE}/bot{self.config.bot_token}/sendMessage"
        payload = {
            "chat_id": self.config.chat_id,
            "text": safe_text,
            "disable_web_page_preview": True,
        }

        last_status: Optional[int] = None
        last_err = ""
        for attempt in range(self.config.max_retries + 1):
            try:
                resp = self._session.post(
                    endpoint,
                    json=payload,
                    timeout=self.config.timeout_seconds,
                )
                last_status = int(getattr(resp, "status_code", 0) or 0)
                if last_status == 200:
                    return TelegramSendResult(sent=True, messages_sent=1, http_status=200, reason="ok")

                if last_status == 429:
                    retry_after_hdr = str(getattr(resp, "headers", {}).get("Retry-After", "") or "")
                    wait_secs = float(retry_after_hdr) if retry_after_hdr.replace(".", "", 1).isdigit() else 2.0
                    last_err = f"Telegram notification failed: HTTP 429 retry-after={retry_after_hdr or 'none'}"
                    if attempt < self.config.max_retries:
                        self._sleep(min(wait_secs, 30.0))
                        continue
                    logger.warning("%s", last_err)
                    return TelegramSendResult(sent=False, http_status=429, reason=last_err, errors=[last_err])

                if last_status >= 500:
                    last_err = f"Telegram notification failed: HTTP {last_status}"
                    if attempt < self.config.max_retries:
                        self._sleep(min(1.5 * (attempt + 1), 10.0))
                        continue
                    logger.warning("%s", last_err)
                    return TelegramSendResult(sent=False, http_status=last_status, reason=last_err, errors=[last_err])

                # Non-retryable 4xx (never print token)
                last_err = f"Telegram notification failed: HTTP {last_status}"
                logger.warning("%s", last_err)
                return TelegramSendResult(sent=False, http_status=last_status, reason=last_err, errors=[last_err])
            except Exception as exc:
                safe_exc = _redact_token(f"{type(exc).__name__}: {exc}", self.config.bot_token)
                last_err = f"Telegram notification failed: {safe_exc}"
                if attempt < self.config.max_retries:
                    self._sleep(min(1.5 * (attempt + 1), 10.0))
                    continue
                logger.warning("%s", last_err)
                return TelegramSendResult(sent=False, http_status=last_status, reason=last_err, errors=[last_err])

        return TelegramSendResult(sent=False, http_status=last_status, reason=last_err, errors=[last_err])

    def send_sync_report(self, report: SyncRunReport) -> TelegramSendResult:
        """Best-effort send of a SyncRunReport. Guaranteed never to raise an exception."""
        try:
            ready, reason = self.config.is_ready()
            if not ready:
                return TelegramSendResult(sent=False, skipped=True, reason=reason)

            chunks = self.split_report_messages(report)
            sent_count = 0
            errors: List[str] = []
            last_status: Optional[int] = None
            for chunk in chunks:
                res = self.send_message(chunk)
                last_status = res.http_status
                if res.sent:
                    sent_count += 1
                else:
                    errors.extend(res.errors or [res.reason])
                    break
            return TelegramSendResult(
                sent=(sent_count == len(chunks) and sent_count > 0),
                messages_sent=sent_count,
                http_status=last_status,
                reason="ok" if sent_count == len(chunks) else (errors[0] if errors else "failed"),
                errors=errors,
            )
        except Exception as exc:
            safe_exc = _redact_token(f"{type(exc).__name__}: {exc}", self.config.bot_token)
            logger.warning("Telegram send_sync_report suppressed error: %s", safe_exc)
            return TelegramSendResult(sent=False, reason=safe_exc, errors=[safe_exc])
        finally:
            if self._owns_session and self._session is not None:
                try:
                    self._session.close()
                except Exception:
                    pass
