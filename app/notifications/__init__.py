"""CINEMY notification services (Telegram Bot API sync reports)."""
from .models import (
    OverallStatus,
    SourceRunReport,
    SourceStatus,
    SyncRunReport,
    build_sync_run_report,
    compute_overall_status,
    source_report_from_dict,
)
from .ntfy import (
    NTFY_SAFE_MAX_LENGTH,
    NtfyConfig,
    NtfyNotifier,
    NtfySendResult,
)
from .telegram import (
    TELEGRAM_SAFE_MAX_LENGTH,
    TelegramConfig,
    TelegramNotifier,
    TelegramSendResult,
)

__all__ = [
    "OverallStatus",
    "SourceRunReport",
    "SourceStatus",
    "SyncRunReport",
    "NTFY_SAFE_MAX_LENGTH",
    "NtfyConfig",
    "NtfyNotifier",
    "NtfySendResult",
    "TELEGRAM_SAFE_MAX_LENGTH",
    "TelegramConfig",
    "TelegramNotifier",
    "TelegramSendResult",
    "build_sync_run_report",
    "compute_overall_status",
    "source_report_from_dict",
]
