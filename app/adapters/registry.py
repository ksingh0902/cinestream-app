from __future__ import annotations

from .base import SourceAdapter
from .ask4movie import adapter as ask4movie
from .yomovies import adapter as yomovies          # EXISTING — wrap only

ADAPTERS: dict[str, SourceAdapter] = {a.key: a for a in (yomovies, ask4movie)}


def get(key: str) -> SourceAdapter | None:
    return ADAPTERS.get(key)


def health() -> dict:
    out = {}
    for key, ad in ADAPTERS.items():
        try:
            out[key] = {"label": ad.label, "kind": ad.player_kind, **ad.health()}
        except Exception as exc:                                  # noqa: BLE001
            out[key] = {"label": ad.label, "kind": ad.player_kind,
                        "ok": False, "detail": str(exc)[:200], "items": 0}
    return out
