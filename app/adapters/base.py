"""Unified source-adapter contract. Adapters share THIS and nothing else."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Optional


@dataclass
class MediaItem:
    source: str
    source_id: str
    title: str
    year: Optional[int] = None
    language: Optional[str] = None
    language_code: Optional[str] = None
    poster_url: Optional[str] = None
    duration_s: Optional[int] = None
    rating: Optional[float] = None
    genres: str = ""
    synopsis: str = ""
    tmdb_id: Optional[int] = None
    is_series: bool = False
    detail_url: Optional[str] = None      # permanent upstream page
    player_kind: str = "iframe"           # 'hls' | 'iframe'


@dataclass
class StreamInfo:
    kind: str                             # 'hls' | 'iframe'
    url: str
    servers: list = field(default_factory=list)   # [{"label": ..., "url": ...}]
    headers: dict = field(default_factory=dict)   # headers the player must send
    ttl_s: int = 0                        # 0 = stable until upstream changes


class SourceAdapter(ABC):
    key: str = "base"
    label: str = "Base"
    player_kind: str = "iframe"
    homepage: str = ""

    @abstractmethod
    def health(self) -> dict:
        """{"ok": bool, "detail": str, "items": int} — must never raise."""

    @abstractmethod
    def iter_catalog(self, *, max_pages: int = 0) -> Iterator[MediaItem]:
        """Yield MediaItems, newest first. max_pages=0 means 'all'."""

    @abstractmethod
    def enrich(self, item: MediaItem) -> MediaItem:
        """Fill poster / language / runtime / synopsis from the detail page."""

    @abstractmethod
    def resolve_stream(self, detail_url: str) -> StreamInfo:
        """Return a FRESH playable StreamInfo for a permanent detail_url."""
