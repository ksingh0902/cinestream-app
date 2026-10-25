from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Tuple

from .config import (
    ADMIN_USERNAME,
    RATE_LIMIT_LOCKOUT_SECONDS,
    SESSION_MAX_AGE_SECONDS,
    VIEWER_USERNAME,
)
from .security import (
    generate_session_id,
    hash_password,
    sign_session_token,
    verify_password,
    verify_session_token,
)
from .store import (
    clear_failed_attempts,
    create_session,
    delete_session,
    get_session,
    get_user,
    get_user_by_role,
    increment_role_auth_version,
    record_failed_attempt,
    update_session_activity,
    update_user_password,
)

logger = logging.getLogger("cinemymovies.auth.service")


def authenticate_user(
    username: str,
    password: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """
    Authenticate a user by username and password.
    Returns:
        (user_dict, signed_token, error_message)
    """
    username = (username or "").strip()
    ip_key = f"ip:{ip_address}" if ip_address else None
    user_key = f"user:{username}" if username else None

    # Check rate limit on IP
    if ip_key:
        from .store import check_rate_limit
        allowed, remaining = check_rate_limit(ip_key)
        if not allowed:
            return None, None, f"Too many failed login attempts. Please wait {remaining} seconds."

    # Check rate limit on User
    if user_key:
        from .store import check_rate_limit
        allowed, remaining = check_rate_limit(user_key)
        if not allowed:
            return None, None, f"Account temporarily locked due to failed attempts. Please wait {remaining} seconds."

    user = get_user(username)
    if not user or not verify_password(password, user["password_hash"]):
        # Rate limit failure recording
        if ip_key:
            record_failed_attempt(ip_key)
        if user_key:
            record_failed_attempt(user_key)
        return None, None, "Invalid credentials."

    # Clear rate limits on successful auth
    if ip_key:
        clear_failed_attempts(ip_key)
    if user_key:
        clear_failed_attempts(user_key)

    # Issue session
    session_id, signed_token = issue_user_session(user, ip_address, user_agent)
    return user, signed_token, None


def issue_user_session(
    user: Dict[str, Any],
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Tuple[str, str]:
    """Issue, store, and cryptographically sign a new session for a user."""
    now = int(time.time())
    expires_at = now + SESSION_MAX_AGE_SECONDS
    session_id = generate_session_id()
    auth_version = user.get("auth_version", 1)
    role = user["role"]

    create_session(
        session_id=session_id,
        username=user["username"],
        role=role,
        auth_version=auth_version,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    signed_token = sign_session_token(session_id)
    return session_id, signed_token


def validate_session(signed_token: str) -> Optional[Dict[str, Any]]:
    """
    Validate a signed session cookie.
    Ensures:
      1. HMAC signature is valid.
      2. Session exists in persistent storage.
      3. Session has not expired.
      4. Session's auth_version matches current user auth_version (revocation check).
    """
    session_id = verify_session_token(signed_token)
    if not session_id:
        return None

    sess = get_session(session_id)
    if not sess:
        return None

    now = int(time.time())
    if sess["expires_at"] < now:
        delete_session(session_id)
        return None

    # Check user record and verify auth_version
    user = get_user(sess["username"])
    if not user:
        delete_session(session_id)
        return None

    if sess["auth_version"] != user["auth_version"]:
        # Session was revoked!
        logger.info(
            "Session %s revoked: session version %d != current version %d",
            session_id,
            sess["auth_version"],
            user["auth_version"],
        )
        delete_session(session_id)
        return None

    # Update activity timestamp periodically (every 5 minutes)
    if now - sess["last_activity"] > 300:
        update_session_activity(session_id)

    return {**sess, "user": user}


def terminate_session(signed_token: str) -> None:
    """Terminate an individual session upon logout."""
    session_id = verify_session_token(signed_token)
    if session_id:
        delete_session(session_id)


def admin_change_viewer_password(
    current_admin_password: str,
    new_viewer_password: str,
    admin_username: str,
) -> Tuple[bool, Optional[str]]:
    """
    Admin action: Update shared viewer password.
    Atomically revokes all existing viewer sessions.
    """
    admin_user = get_user(admin_username)
    if not admin_user or not verify_password(current_admin_password, admin_user["password_hash"]):
        return False, "Current administrator password is incorrect."

    if not new_viewer_password or len(new_viewer_password.strip()) < 6:
        return False, "Viewer password must be at least 6 characters long."

    viewer_user = get_user_by_role("viewer")
    viewer_username = viewer_user["username"] if viewer_user else VIEWER_USERNAME

    new_hash = hash_password(new_viewer_password.strip())
    new_version = update_user_password(viewer_username, new_hash)
    logger.info("Admin %s updated viewer password. New viewer auth_version: %d", admin_username, new_version)
    return True, None


def admin_sign_out_all_viewers(
    current_admin_password: str,
    admin_username: str,
) -> Tuple[bool, Optional[str]]:
    """
    Admin action: Sign out all viewer devices without changing the password.
    Atomically increments viewer auth_version and purges active viewer sessions.
    """
    admin_user = get_user(admin_username)
    if not admin_user or not verify_password(current_admin_password, admin_user["password_hash"]):
        return False, "Current administrator password is incorrect."

    new_version = increment_role_auth_version("viewer")
    logger.info("Admin %s revoked all viewer sessions. New viewer auth_version: %d", admin_username, new_version)
    return True, None


def admin_change_admin_password(
    current_admin_password: str,
    new_admin_password: str,
    admin_username: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Admin action: Change admin's own password.
    Revokes other admin sessions and issues a fresh session for current request.
    """
    admin_user = get_user(admin_username)
    if not admin_user or not verify_password(current_admin_password, admin_user["password_hash"]):
        return False, "Current administrator password is incorrect.", None

    if not new_admin_password or len(new_admin_password.strip()) < 8:
        return False, "New administrator password must be at least 8 characters long.", None

    new_hash = hash_password(new_admin_password.strip())
    new_version = update_user_password(admin_username, new_hash)

    # Issue a fresh session for the current administrator
    now = int(time.time())
    expires_at = now + SESSION_MAX_AGE_SECONDS
    new_session_id = generate_session_id()
    create_session(
        session_id=new_session_id,
        username=admin_username,
        role="admin",
        auth_version=new_version,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    new_token = sign_session_token(new_session_id)

    logger.info("Admin %s updated password. New auth_version: %d", admin_username, new_version)
    return True, None, new_token
