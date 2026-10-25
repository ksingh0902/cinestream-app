from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from typing import Optional
from urllib.parse import urlparse

import bcrypt

from .config import SESSION_SECRET


def hash_password(password: str) -> str:
    """Hash a plain text password using bcrypt with 12 rounds of work."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash in constant time."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def generate_session_id() -> str:
    """Generate a cryptographically secure random session ID."""
    return secrets.token_urlsafe(32)


def sign_session_token(session_id: str) -> str:
    """Sign a session ID using HMAC-SHA256 with server's SESSION_SECRET."""
    signature = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        session_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{session_id}.{signature}"


def verify_session_token(token: str) -> Optional[str]:
    """Verify an HMAC-signed session token. Return session_id if valid, else None."""
    if not token or "." not in token:
        return None
    session_id, signature = token.split(".", 1)
    expected_sig = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        session_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if hmac.compare_digest(signature, expected_sig):
        return session_id
    return None


def generate_csrf_token() -> str:
    """Generate a random CSRF protection token."""
    return secrets.token_urlsafe(32)


def verify_csrf_token(token_a: str, token_b: str) -> bool:
    """Verify two CSRF tokens match in constant time."""
    if not token_a or not token_b:
        return False
    return hmac.compare_digest(str(token_a), str(token_b))


def sanitize_redirect_url(target: str, default: str = "/") -> str:
    """Prevent open-redirect vulnerabilities. Only allow safe relative application paths."""
    if not target or not isinstance(target, str):
        return default
    target = target.strip()
    # Must start with exactly one forward slash, not '//' or '/\'
    if not target.startswith("/") or target.startswith("//") or target.startswith("/\\"):
        return default
    # Reject dangerous schemes or protocols
    if any(k in target.lower() for k in ("javascript:", "data:", "vbscript:", "@")):
        return default
    # Parse URL to ensure it has no external scheme or netloc
    try:
        parsed = urlparse(target)
        if parsed.scheme or parsed.netloc:
            return default
        return target
    except Exception:
        return default
