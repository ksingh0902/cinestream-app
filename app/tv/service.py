"""Business logic and security validation for CINEMY TV Pairing & Authorization."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

from app.auth.config import SESSION_SECRET
from . import store

PAIRING_TTL_SECONDS = 180  # 3 minutes
PAIRING_MAX_FAILED_ATTEMPTS = 5
TV_ONLINE_WINDOW_SECONDS = 90

_TV_ID_RE = re.compile(r"^tv_[a-zA-Z0-9_-]{8,40}$")


class TvPairingError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "tv_pairing_error"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _hash_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def hash_client_ip(ip: Optional[str]) -> Optional[str]:
    clean = (ip or "").strip()
    if not clean:
        return None
    return hmac.new(
        SESSION_SECRET.encode("utf-8"),
        f"tv-ip:{clean}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]


def _normalize_code(raw: str) -> str:
    return re.sub(r"[^0-9]", "", raw or "")


def _format_display_code(digits: str) -> str:
    if len(digits) == 6:
        return f"{digits[:3]} {digits[3:]}"
    return digits


def _sanitize_device_name(name: Optional[str], default: str) -> str:
    cleaned = re.sub(r"\s+", " ", (name or "").strip())[:60]
    return cleaned or default


def register_tv(
    *,
    owner_username: str,
    name: Optional[str] = None,
    tv_id: Optional[str] = None,
    device_secret: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Register a new persistent TV identity or refresh an existing TV's name/presence.
    If an existing tv_id is supplied, caller must own it (and supply valid device_secret if rotating).
    """
    clean_name = _sanitize_device_name(name, "Living Room TV")
    ip_hash = hash_client_ip(client_ip)
    now = int(time.time())

    issued_secret: Optional[str] = None
    if tv_id:
        tv_id = tv_id.strip()
        if not _TV_ID_RE.match(tv_id):
            raise TvPairingError("Invalid TV identifier format.", 400, "invalid_tv_id")
        existing = store.get_tv_device(tv_id)
        if existing:
            if existing["owner_username"] != owner_username:
                raise TvPairingError("TV device belongs to another account.", 403, "forbidden_tv")
            if existing.get("revoked_at") is None and device_secret:
                if not hmac.compare_digest(existing["device_secret_hash"], _hash_secret(device_secret)):
                    raise TvPairingError("Invalid TV device secret.", 403, "invalid_device_secret")
                secret_hash = existing["device_secret_hash"]
            else:
                issued_secret = secrets.token_urlsafe(32)
                secret_hash = _hash_secret(issued_secret)
        else:
            issued_secret = secrets.token_urlsafe(32)
            secret_hash = _hash_secret(issued_secret)
    else:
        tv_id = f"tv_{secrets.token_hex(8)}"
        issued_secret = secrets.token_urlsafe(32)
        secret_hash = _hash_secret(issued_secret)

    record = store.upsert_tv_device(
        tv_id=tv_id,
        owner_username=owner_username,
        name=clean_name,
        device_secret_hash=secret_hash,
        ip_hash=ip_hash,
        now=now,
    )
    controllers = store.list_active_controllers_for_tv(tv_id)
    out: Dict[str, Any] = {
        "tv_id": record["tv_id"],
        "name": record["name"],
        "last_seen_at": record["last_seen_at"],
        "created_at": record["created_at"],
        "controllers": [
            {
                "controller_id": c["controller_id"],
                "phone_name": c["phone_name"],
                "role": c["role"],
                "created_at": c["created_at"],
                "last_seen_at": c["last_seen_at"],
            }
            for c in controllers
        ],
    }
    if issued_secret is not None:
        out["device_secret"] = issued_secret
    return out


def start_pairing(
    *,
    owner_username: str,
    tv_id: str,
    client_ip: Optional[str] = None,
    ttl_seconds: int = PAIRING_TTL_SECONDS,
) -> Dict[str, Any]:
    """
    Create a short-lived, single-use pairing session for a TV device.
    Returns QR payload (without any permanent credentials) and a 6-digit fallback code.
    """
    tv = store.get_tv_device(tv_id)
    if not tv or tv.get("revoked_at") is not None:
        raise TvPairingError("TV device not found or revoked.", 404, "tv_not_found")
    if tv["owner_username"] != owner_username:
        raise TvPairingError("Not authorized for this TV device.", 403, "forbidden_tv")

    now = int(time.time())
    bounded_ttl = max(30, min(600, int(ttl_seconds)))
    expires_at = now + bounded_ttl

    pairing_id = f"pair_{secrets.token_hex(8)}"
    raw_token = secrets.token_urlsafe(24)
    raw_code = f"{secrets.randbelow(1_000_000):06d}"

    store.update_tv_presence(tv_id, hash_client_ip(client_ip), now=now)
    store.create_pairing_session(
        pairing_id=pairing_id,
        tv_id=tv_id,
        owner_username=owner_username,
        code_hash=_hash_secret(raw_code),
        token_hash=_hash_secret(raw_token),
        expires_at=expires_at,
        now=now,
    )

    return {
        "pairing_id": pairing_id,
        "tv_id": tv_id,
        "tv_name": tv["name"],
        "code": raw_code,
        "display_code": _format_display_code(raw_code),
        "pairing_token": raw_token,
        "qr_path": f"/remote?pid={pairing_id}&t={raw_token}",
        "expires_at": expires_at,
        "ttl_seconds": bounded_ttl,
    }


def complete_pairing(
    *,
    owner_username: str,
    pairing_id: Optional[str] = None,
    pairing_token: Optional[str] = None,
    code: Optional[str] = None,
    phone_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Complete pairing via either:
      1. QR payload (pairing_id + pairing_token), or
      2. 6-digit fallback code (code).
    Validates owner isolation, expiration, single-use, and rate limits.
    Issues a scoped, revocable controller_id + control_token.
    """
    now = int(time.time())
    session: Optional[Dict[str, Any]] = None

    if pairing_id and pairing_token:
        session = store.get_pairing_session_by_id(pairing_id.strip())
        if not session:
            raise TvPairingError("Invalid or unknown pairing session.", 404, "pairing_not_found")
        if session["owner_username"] != owner_username:
            raise TvPairingError("This pairing code belongs to a different account.", 403, "forbidden_pairing")
        if session.get("consumed_at") is not None:
            raise TvPairingError("This pairing code has already been used.", 410, "pairing_already_used")
        if int(session["expires_at"]) < now:
            raise TvPairingError("This pairing code has expired. Generate a new code on your TV.", 410, "pairing_expired")
        if int(session.get("failed_attempts") or 0) >= PAIRING_MAX_FAILED_ATTEMPTS:
            raise TvPairingError("Too many invalid attempts. Generate a new code on your TV.", 429, "pairing_locked")
        if not hmac.compare_digest(session["token_hash"], _hash_secret(pairing_token.strip())):
            store.increment_pairing_failed_attempts(session["pairing_id"])
            raise TvPairingError("Invalid pairing token.", 400, "invalid_pairing_token")
    elif code:
        digits = _normalize_code(code)
        if len(digits) != 6:
            raise TvPairingError("Enter a valid 6-digit TV code.", 400, "invalid_code_format")
        candidate_hash = _hash_secret(digits)
        active_sessions = store.list_recent_pairing_sessions_for_user(owner_username, now=now)
        matched = None
        for s in active_sessions:
            if int(s.get("failed_attempts") or 0) >= PAIRING_MAX_FAILED_ATTEMPTS:
                continue
            if hmac.compare_digest(s["code_hash"], candidate_hash):
                matched = s
                break
        if not matched:
            # Increment attempts on active sessions to prevent 6-digit brute force
            for s in active_sessions[:3]:
                store.increment_pairing_failed_attempts(s["pairing_id"])
            raise TvPairingError("Invalid or expired 6-digit TV code.", 400, "invalid_or_expired_code")
        session = matched
    else:
        raise TvPairingError("Provide either QR pairing credentials or a 6-digit TV code.", 400, "missing_credentials")

    tv = store.get_tv_device(session["tv_id"])
    if not tv or tv.get("revoked_at") is not None or tv["owner_username"] != owner_username:
        raise TvPairingError("Target TV is no longer available.", 404, "tv_not_found")

    # Atomically consume the single-use pairing session
    if not store.consume_pairing_session(session["pairing_id"], now=now):
        raise TvPairingError("This pairing code has already been used.", 410, "pairing_already_used")

    existing_controllers = store.list_active_controllers_for_tv(tv["tv_id"])
    controller_role = "primary" if len(existing_controllers) == 0 else "secondary"

    controller_id = f"ctrl_{secrets.token_hex(8)}"
    raw_control_token = secrets.token_urlsafe(32)
    clean_phone = _sanitize_device_name(phone_name, "Mobile Remote")

    ctrl = store.create_authorized_controller(
        controller_id=controller_id,
        tv_id=tv["tv_id"],
        owner_username=owner_username,
        phone_name=clean_phone,
        role=controller_role,
        control_token_hash=_hash_secret(raw_control_token),
        now=now,
    )

    return {
        "paired": True,
        "tv_id": tv["tv_id"],
        "tv_name": tv["name"],
        "controller_id": ctrl["controller_id"],
        "phone_name": ctrl["phone_name"],
        "role": ctrl["role"],
        "control_token": raw_control_token,
        "created_at": ctrl["created_at"],
    }


def list_devices(
    *,
    owner_username: str,
    client_ip: Optional[str] = None,
    online_tv_ids: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    """
    List all active TVs for the authenticated user, annotated with:
      - online status (realtime connection or recent heartbeat)
      - same_network / nearby flag (matching hashed egress IP)
      - active authorized controllers
    """
    now = int(time.time())
    caller_ip_hash = hash_client_ip(client_ip)
    devices = store.list_tv_devices_for_user(owner_username)
    live_ids = online_tv_ids or set()

    result: List[Dict[str, Any]] = []
    for d in devices:
        controllers = store.list_active_controllers_for_tv(d["tv_id"])
        is_online = (
            d["tv_id"] in live_ids
            or (now - int(d.get("last_seen_at") or 0)) <= TV_ONLINE_WINDOW_SECONDS
        )
        same_network = bool(
            caller_ip_hash and d.get("last_ip_hash") and hmac.compare_digest(caller_ip_hash, d["last_ip_hash"])
        )
        result.append({
            "tv_id": d["tv_id"],
            "name": d["name"],
            "online": is_online,
            "nearby": bool(is_online and same_network),
            "same_network": same_network,
            "last_seen_at": d["last_seen_at"],
            "created_at": d["created_at"],
            "controller_count": len(controllers),
            "controllers": [
                {
                    "controller_id": c["controller_id"],
                    "phone_name": c["phone_name"],
                    "role": c["role"],
                    "created_at": c["created_at"],
                    "last_seen_at": c["last_seen_at"],
                }
                for c in controllers
            ],
        })
    return result


def verify_tv_credentials(tv_id: str, device_secret: str, owner_username: Optional[str] = None) -> Optional[Dict[str, Any]]:
    tv = store.get_tv_device(tv_id)
    if not tv or tv.get("revoked_at") is not None:
        return None
    if owner_username and tv["owner_username"] != owner_username:
        return None
    if not device_secret or not hmac.compare_digest(tv["device_secret_hash"], _hash_secret(device_secret)):
        return None
    return tv


def verify_controller_credentials(
    controller_id: str,
    control_token: str,
    tv_id: Optional[str] = None,
    owner_username: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    ctrl = store.get_controller(controller_id)
    if not ctrl or ctrl.get("revoked_at") is not None:
        return None
    if tv_id and ctrl["tv_id"] != tv_id:
        return None
    if owner_username and ctrl["owner_username"] != owner_username:
        return None
    tv = store.get_tv_device(ctrl["tv_id"])
    if not tv or tv.get("revoked_at") is not None:
        return None
    if not control_token or not hmac.compare_digest(ctrl["control_token_hash"], _hash_secret(control_token)):
        return None
    return ctrl


def revoke_controllers(
    *,
    owner_username: str,
    tv_id: str,
    controller_id: Optional[str] = None,
) -> Tuple[bool, int]:
    tv = store.get_tv_device(tv_id)
    if not tv or tv["owner_username"] != owner_username:
        raise TvPairingError("TV device not found.", 404, "tv_not_found")
    if controller_id:
        ok = store.revoke_controller(controller_id, owner_username)
        return ok, (1 if ok else 0)
    count = store.revoke_all_controllers_for_tv(tv_id, owner_username)
    return True, count


def delete_tv(*, owner_username: str, tv_id: str) -> bool:
    ok = store.revoke_tv_device(tv_id, owner_username)
    if not ok:
        raise TvPairingError("TV device not found.", 404, "tv_not_found")
    return True
