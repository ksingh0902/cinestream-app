"""Homepage Discovery API endpoints: Trending Now & Recommended for You."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from ..discovery.popular import (
    DEFAULT_EVERGREEN_LIMIT,
    MAX_EVERGREEN_LIMIT,
    get_evergreen_titles,
)
from ..discovery.recommendations import (
    DEFAULT_REC_LIMIT,
    MAX_REC_LIMIT,
    MAX_SEED_IDS,
    get_recommended_titles,
)
from ..discovery.trending import (
    DEFAULT_TRENDING_LIMIT,
    MAX_TRENDING_LIMIT,
    get_trending_titles,
)

router = APIRouter()


def _parse_id_csv(raw: Optional[str]) -> list[int]:
    if not raw:
        return []
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            val = int(part)
            if val > 0:
                out.append(val)
                if len(out) >= MAX_SEED_IDS:
                    break
    return out


def _resolve_authenticated_viewer_key(request: Request) -> str:
    """
    Resolve viewer identity strictly from the server-side auth session attached by
    PrivateAccessMiddleware. Never trusts a client-supplied user_id.
    """
    session = getattr(request.state, "session", None)
    if not isinstance(session, dict):
        raise HTTPException(status_code=401, detail="Authentication required")
    username = str(session.get("username") or "").strip()
    role = str(session.get("role") or "viewer").strip()
    if not username:
        user_obj = getattr(request.state, "user", None)
        if isinstance(user_obj, dict):
            username = str(user_obj.get("username") or "").strip()
            role = str(user_obj.get("role") or role).strip()
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")
    return f"{role.lower()}:{username.lower()}"


@router.get("/api/discovery/trending")
def discovery_trending(
    limit: int = Query(default=DEFAULT_TRENDING_LIMIT, ge=1, le=MAX_TRENDING_LIMIT),
    window_days: int = Query(default=14, ge=1, le=90),
):
    """Aggregate Trending Now discovery row (bounded 1..50, default 50)."""
    return get_trending_titles(limit=limit, window_days=window_days)


@router.get("/api/discovery/evergreen")
def discovery_evergreen(
    limit: int = Query(default=DEFAULT_EVERGREEN_LIMIT, ge=1, le=MAX_EVERGREEN_LIMIT),
    exclude_ids: Optional[str] = Query(default=None, max_length=1024),
):
    """Evergreen Picks discovery row (bounded 1..50, default 50, year-independent, excludes animation)."""
    return get_evergreen_titles(limit=limit, exclude_ids=_parse_id_csv(exclude_ids))


@router.get("/api/discovery/popular")
def discovery_popular(
    limit: int = Query(default=DEFAULT_EVERGREEN_LIMIT, ge=1, le=MAX_EVERGREEN_LIMIT),
    exclude_ids: Optional[str] = Query(default=None, max_length=1024),
):
    """Backwards-compatible alias for Evergreen Picks (bounded 1..50, default 50)."""
    return get_evergreen_titles(limit=limit, exclude_ids=_parse_id_csv(exclude_ids))


@router.get("/api/discovery/recommended")
def discovery_recommended(
    request: Request,
    limit: int = Query(default=DEFAULT_REC_LIMIT, ge=1, le=MAX_REC_LIMIT),
    seed_ids: Optional[str] = Query(default=None, max_length=512),
    exclude_ids: Optional[str] = Query(default=None, max_length=512),
):
    """
    Personalized Recommended for You discovery row scoped strictly to the
    authenticated viewer's server-side session identity.
    """
    viewer_key = _resolve_authenticated_viewer_key(request)
    return get_recommended_titles(
        viewer_key,
        limit=limit,
        seed_ids=_parse_id_csv(seed_ids),
        exclude_ids=_parse_id_csv(exclude_ids),
    )
