"""Structured sync run reporting models for CINEMY observability."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence


class OverallStatus(str, Enum):
    SUCCESS = "SUCCESS"
    SUCCESS_WITH_WARNINGS = "SUCCESS_WITH_WARNINGS"
    FAILED = "FAILED"


class SourceStatus(str, Enum):
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass
class SourceRunReport:
    source: str
    status: SourceStatus = SourceStatus.SUCCESS
    started_at: Optional[int] = None
    finished_at: Optional[int] = None
    discovered: Optional[int] = None
    processed: Optional[int] = None
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    duplicates: int = 0
    quality_upgrades: Optional[int] = None
    quality_downgrades: Optional[int] = None
    metadata_enriched: Optional[int] = None
    playback_found: Optional[int] = None
    playback_missing: Optional[int] = None
    errors: int = 0
    warnings: List[str] = field(default_factory=list)
    http_status: Optional[int] = None
    blocked_reason: Optional[str] = None


@dataclass
class SyncRunReport:
    run_id: str
    started_at: int
    finished_at: int
    duration_seconds: float
    overall_status: OverallStatus
    sources: List[SourceRunReport] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error_summary: Optional[str] = None
    catalogue_total: Optional[int] = None

    @property
    def total_new(self) -> int:
        return sum(max(0, int(s.inserted or 0)) for s in self.sources)

    @property
    def total_updated(self) -> int:
        return sum(max(0, int(s.updated or 0)) for s in self.sources)

    @property
    def total_duplicates(self) -> int:
        return sum(max(0, int(s.duplicates or s.skipped or 0)) for s in self.sources)

    @property
    def total_quality_upgrades(self) -> Optional[int]:
        vals = [int(s.quality_upgrades) for s in self.sources if s.quality_upgrades is not None]
        return sum(vals) if vals else None


def source_report_from_dict(
    source_name: str,
    res: Optional[Dict[str, Any]],
    *,
    started_at: Optional[int] = None,
    finished_at: Optional[int] = None,
    exception: Optional[BaseException] = None,
) -> SourceRunReport:
    """Build an honest SourceRunReport from an adapter's actual return dictionary without inventing metrics."""
    if exception is not None:
        return SourceRunReport(
            source=source_name,
            status=SourceStatus.FAILED,
            started_at=started_at,
            finished_at=finished_at,
            errors=1,
            warnings=[f"{source_name} failed: {type(exception).__name__}: {exception}"],
        )

    data = res if isinstance(res, dict) else {}
    total = data.get("total")
    added = int(data.get("added") or 0)
    updated = int(data.get("updated") or 0)
    skipped = int(data.get("skipped") or 0)
    upgraded = data.get("upgraded")
    downgraded = data.get("downgrades_rejected")
    http_status = data.get("http_status")
    blocked_reason = data.get("blocked_reason")
    warnings: List[str] = list(data.get("warnings") or [])

    status = SourceStatus.SUCCESS
    if str(data.get("status") or "").upper() == "BLOCKED" or blocked_reason:
        status = SourceStatus.BLOCKED
    elif str(data.get("status") or "").upper() == "FAILED":
        status = SourceStatus.FAILED
    elif source_name.lower() in ("yomovies", "prmovies") and total == 0 and added == 0 and updated == 0:
        status = SourceStatus.WARNING
        warnings.append(f"{source_name} returned 0 URLs (upstream may be unavailable or challenged)")

    return SourceRunReport(
        source=source_name,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        discovered=int(total) if total is not None else None,
        processed=(added + updated + skipped) if total is not None else None,
        inserted=added,
        updated=updated,
        skipped=skipped,
        duplicates=skipped,
        quality_upgrades=int(upgraded) if upgraded is not None else None,
        quality_downgrades=int(downgraded) if downgraded is not None else None,
        errors=int(data.get("errors") or 0),
        warnings=warnings,
        http_status=int(http_status) if http_status is not None else None,
        blocked_reason=str(blocked_reason) if blocked_reason else None,
    )


def compute_overall_status(sources: Sequence[SourceRunReport], *, fatal_error: Optional[str] = None) -> OverallStatus:
    """Determine overall sync status without treating a single blocked source as total failure."""
    if fatal_error:
        return OverallStatus.FAILED
    if not sources:
        return OverallStatus.FAILED
    if all(s.status == SourceStatus.FAILED for s in sources):
        return OverallStatus.FAILED
    if any(s.status in (SourceStatus.WARNING, SourceStatus.BLOCKED, SourceStatus.FAILED) or s.warnings or s.errors > 0 for s in sources):
        return OverallStatus.SUCCESS_WITH_WARNINGS
    return OverallStatus.SUCCESS


def build_sync_run_report(
    sources: Sequence[SourceRunReport],
    *,
    started_at: int,
    finished_at: int,
    run_id: Optional[str] = None,
    fatal_error: Optional[str] = None,
    catalogue_total: Optional[int] = None,
) -> SyncRunReport:
    source_list = list(sources)
    overall = compute_overall_status(source_list, fatal_error=fatal_error)
    warnings: List[str] = []
    for s in source_list:
        if s.status == SourceStatus.BLOCKED:
            detail = f"HTTP {s.http_status}" if s.http_status else (s.blocked_reason or "BLOCKED")
            warnings.append(f"{s.source} {detail}")
        for w in s.warnings:
            if w not in warnings:
                warnings.append(w)

    return SyncRunReport(
        run_id=run_id or f"sync-{started_at}-{uuid.uuid4().hex[:6]}",
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=round(max(0.0, float(finished_at - started_at)), 2),
        overall_status=overall,
        sources=source_list,
        warnings=warnings,
        error_summary=fatal_error,
        catalogue_total=catalogue_total,
    )
