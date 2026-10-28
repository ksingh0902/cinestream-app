from __future__ import annotations

import logging
import sqlite3
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from . import config
from .config import (
    ADMIN_INITIAL_PASSWORD,
    ADMIN_USERNAME,
    RATE_LIMIT_LOCKOUT_SECONDS,
    RATE_LIMIT_MAX_ATTEMPTS,
    VIEWER_INITIAL_PASSWORD,
    VIEWER_USERNAME,
    get_setup_lockfile_path,
)
from .security import hash_password
from .database import connect as get_db_connection, lock_initialization

logger = logging.getLogger("cinemymovies.auth.store")


class AuthSystemState(str, Enum):
    INITIALIZED = "initialized"
    GENUINELY_UNINITIALIZED = "uninitialized"
    STORAGE_UNAVAILABLE = "storage_unavailable"


DDL_STATEMENTS = """
CREATE TABLE IF NOT EXISTS auth_users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    auth_version INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    role TEXT NOT NULL,
    auth_version INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    last_activity INTEGER NOT NULL,
    ip_address TEXT,
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(username);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_role ON auth_sessions(role);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions(expires_at);

CREATE TABLE IF NOT EXISTS auth_login_attempts (
    key TEXT PRIMARY KEY,
    failure_count INTEGER NOT NULL DEFAULT 0,
    locked_until INTEGER NOT NULL DEFAULT 0,
    last_attempt INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def write_setup_lockfile() -> None:
    """Retain a local development lock marker; production uses shared database state."""
    if config.AUTH_DATABASE_URL:
        return
    try:
        lock_path = get_setup_lockfile_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(f"setup_locked_at={int(time.time())}\n", encoding="utf-8")
    except Exception as e:
        logger.warning("Could not write setup lockfile: %s", e)


def has_setup_lockfile() -> bool:
    """Check if the persistent setup lockfile exists."""
    return get_setup_lockfile_path().exists()


def get_meta_value(key: str) -> Optional[str]:
    """Retrieve metadata flag from auth_meta table."""
    with get_db_connection() as conn:
        row = conn.execute("SELECT value FROM auth_meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_meta_value(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Store or update metadata flag in auth_meta table."""
    conn.execute(
        "INSERT INTO auth_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_auth_system_state() -> Tuple[AuthSystemState, Optional[str]]:
    try:
        with get_db_connection() as conn:
            marker = conn.execute("SELECT value FROM auth_meta WHERE key = 'setup_completed'").fetchone()
            users = conn.execute("SELECT password_hash, role FROM auth_users").fetchall()
            valid = any(u["password_hash"] and u["role"] in ("admin", "viewer") for u in users)
            if valid:
                return AuthSystemState.INITIALIZED, None
            if users or (marker and marker["value"] == "1") or (not config.AUTH_DATABASE_URL and has_setup_lockfile()):
                return AuthSystemState.STORAGE_UNAVAILABLE, "Existing authentication records require recovery"
            if not config.ALLOW_PUBLIC_SETUP:
                return AuthSystemState.STORAGE_UNAVAILABLE, "Authentication must be provisioned by the operator"
            return AuthSystemState.GENUINELY_UNINITIALIZED, None
    except Exception:
        logger.exception("Authentication storage state check failed")
        return AuthSystemState.STORAGE_UNAVAILABLE, "Authentication storage unavailable"


def is_setup_completed() -> bool:
    """Check if initial setup has been completed and is locked."""
    state, _ = get_auth_system_state()
    return state == AuthSystemState.INITIALIZED


def complete_initial_setup(
    admin_password: str,
    viewer_password: str,
    admin_username: str = ADMIN_USERNAME,
    viewer_username: str = VIEWER_USERNAME,
) -> Tuple[bool, Optional[str]]:
    """
    Complete initial setup by setting admin and viewer passwords.
    PERMANENTLY LOCKED once initialized. Never allows public reinitialization or overwriting existing credentials.
    """
    if not config.ALLOW_PUBLIC_SETUP:
        return False, "Public setup is permanently locked."
    state, err = get_auth_system_state()
    if state == AuthSystemState.STORAGE_UNAVAILABLE:
        return False, f"Authentication storage is currently unavailable: {err}"
    if state == AuthSystemState.INITIALIZED:
        return False, "Initial setup has already been completed and is permanently locked."

    if not admin_password or len(admin_password) < 8:
        return False, "Administrator password must be at least 8 characters long."

    if not viewer_password or len(viewer_password) < 6:
        return False, "Shared viewer password must be at least 6 characters long."

    admin_username = admin_username.strip() or "admin"
    viewer_username = viewer_username.strip() or "viewer"
    if admin_username == viewer_username:
        return False, "Admin and viewer usernames must differ."
    now = int(time.time())
    admin_hash = hash_password(admin_password)
    viewer_hash = hash_password(viewer_password)

    try:
        with get_db_connection() as conn:
            lock_initialization(conn)
            existing_count = conn.execute("SELECT COUNT(*) AS cnt FROM auth_users").fetchone()["cnt"]
            marker = conn.execute("SELECT value FROM auth_meta WHERE key = 'setup_completed'").fetchone()
            if existing_count > 0 or (marker and marker["value"] == "1"):
                return False, "Setup is permanently locked. Existing credentials cannot be overwritten."

            conn.execute(
                """
                INSERT INTO auth_users (username, password_hash, role, auth_version, created_at, updated_at)
                VALUES (?, ?, 'admin', 1, ?, ?)
                ON CONFLICT(username) DO NOTHING
                """,
                (admin_username.strip() or "admin", admin_hash, now, now),
            )
            conn.execute(
                """
                INSERT INTO auth_users (username, password_hash, role, auth_version, created_at, updated_at)
                VALUES (?, ?, 'viewer', 1, ?, ?)
                ON CONFLICT(username) DO NOTHING
                """,
                (viewer_username.strip() or "viewer", viewer_hash, now, now),
            )
            set_meta_value(conn, "setup_completed", "1")
            set_meta_value(conn, "setup_locked_at", str(now))
            conn.execute("DELETE FROM auth_login_attempts")
            conn.commit()

        write_setup_lockfile()
        logger.info("Initial setup completed successfully and locked for admin and viewer.")
        return True, None
    except (sqlite3.Error, OSError) as e:
        logger.error("Failed to complete initial setup due to storage error: %s", e)
        raise


def init_auth_db() -> None:
    """Create schema without recreating production credentials on startup."""
    try:
        with get_db_connection() as conn:
            lock_initialization(conn)
            conn.executescript(DDL_STATEMENTS)
        if config.ALLOW_PUBLIC_SETUP and ADMIN_INITIAL_PASSWORD and VIEWER_INITIAL_PASSWORD:
            complete_initial_setup(ADMIN_INITIAL_PASSWORD, VIEWER_INITIAL_PASSWORD)
    except Exception:
        logger.exception("Authentication initialization failed; requests will fail closed")


def get_user(username: str) -> Optional[Dict[str, Any]]:
    """Retrieve user record by username."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT username, password_hash, role, auth_version, created_at, updated_at FROM auth_users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_role(role: str) -> Optional[Dict[str, Any]]:
    """Retrieve user record by role (admin or viewer)."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT username, password_hash, role, auth_version, created_at, updated_at FROM auth_users WHERE role = ? LIMIT 1",
            (role,),
        ).fetchone()
        return dict(row) if row else None


def update_user_password(username: str, new_hash: str) -> int:
    """Update a user's password hash and atomically increment their auth_version to invalidate prior sessions."""
    now = int(time.time())
    actual_hash = new_hash if (new_hash.startswith("$2a$") or new_hash.startswith("$2b$") or new_hash.startswith("$2y$")) else hash_password(new_hash)
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE auth_users
            SET password_hash = ?, auth_version = auth_version + 1, updated_at = ?
            WHERE username = ?
            """,
            (actual_hash, now, username),
        )
        cur.execute("SELECT auth_version, role FROM auth_users WHERE username = ?", (username,))
        row = cur.fetchone()
        new_version = row["auth_version"]
        role = row["role"]
        # Delete prior sessions from store
        cur.execute("DELETE FROM auth_sessions WHERE username = ? OR role = ?", (username, role))
        conn.commit()
        return new_version


def increment_role_auth_version(role: str) -> int:
    """Increment auth_version for all users with the specified role and remove their active sessions."""
    now = int(time.time())
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE auth_users
            SET auth_version = auth_version + 1, updated_at = ?
            WHERE role = ?
            """,
            (now, role),
        )
        cur.execute("SELECT auth_version FROM auth_users WHERE role = ? LIMIT 1", (role,))
        row = cur.fetchone()
        new_version = row["auth_version"] if row else 1
        cur.execute("DELETE FROM auth_sessions WHERE role = ?", (role,))
        conn.commit()
        return new_version


def create_session(
    session_id: str,
    username: str,
    role: str,
    auth_version: int,
    expires_at: int,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Record a newly created session in the database."""
    now = int(time.time())
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO auth_sessions (
                session_id, username, role, auth_version, created_at, expires_at, last_activity, ip_address, user_agent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, username, role, auth_version, now, expires_at, now, ip_address, user_agent),
        )
        conn.commit()


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve session record by session_id."""
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT session_id, username, role, auth_version, created_at, expires_at, last_activity, ip_address, user_agent
            FROM auth_sessions
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        return dict(row) if row else None


def update_session_activity(session_id: str) -> None:
    """Update last_activity timestamp for session."""
    now = int(time.time())
    with get_db_connection() as conn:
        conn.execute("UPDATE auth_sessions SET last_activity = ? WHERE session_id = ?", (now, session_id))
        conn.commit()


def delete_session(session_id: str) -> None:
    """Delete a single session."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE session_id = ?", (session_id,))
        conn.commit()


def delete_sessions_by_role(role: str) -> int:
    """Delete all active sessions for a given role."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM auth_sessions WHERE role = ?", (role,))
        count = cur.rowcount
        conn.commit()
        return count


def delete_expired_sessions() -> int:
    """Purge expired sessions."""
    now = int(time.time())
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (now,))
        count = cur.rowcount
        conn.commit()
        return count


def _device_family(user_agent: Optional[str]) -> str:
    """Reduce a browser user-agent to a coarse device platform.

    Browser names are intentionally ignored so Chrome/Edge/Firefox sessions on
    the same computer can be represented as one estimated device. This is not
    a hardware identifier; the IP address is combined with this family below.
    """
    ua = (user_agent or "").lower()
    if "android" in ua:
        return "android"
    if "iphone" in ua or "ipad" in ua or "ipod" in ua:
        return "ios"
    if "windows" in ua:
        return "windows"
    if "mac os" in ua or "macintosh" in ua:
        return "macos"
    if "cros" in ua:
        return "chromeos"
    if "linux" in ua:
        return "linux"
    return "unknown"


def count_active_sessions() -> Dict[str, int]:
    """Count valid sessions and deduplicated estimated devices by role.

    Every login creates a server session, so counting session rows overstates
    devices when one person uses multiple browsers. A device estimate groups
    active rows by public IP and coarse platform. Logout/revocation removes the
    row immediately; expired rows are purged before counting.
    """
    now = int(time.time())
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (now,))
        conn.commit()
        cur.execute(
            """
            SELECT session_id, role, ip_address, user_agent
            FROM auth_sessions
            WHERE expires_at >= ?
            """,
            (now,),
        )

        counts = {
            "admin": 0,
            "viewer": 0,
            "total": 0,
            "admin_devices": 0,
            "viewer_devices": 0,
            "device_total": 0,
        }
        devices = {"admin": set(), "viewer": set()}
        for row in cur.fetchall():
            role = row["role"]
            if role not in ("admin", "viewer"):
                continue
            counts[role] += 1
            counts["total"] += 1
            ip = (row["ip_address"] or "").strip()
            family = _device_family(row["user_agent"])
            # Missing request metadata should not collapse every legacy row
            # into one fake device; fall back to its unique session id.
            fingerprint = f"{ip}|{family}" if ip else f"session:{row['session_id']}"
            devices[role].add(fingerprint)

        counts["admin_devices"] = len(devices["admin"])
        counts["viewer_devices"] = len(devices["viewer"])
        counts["device_total"] = len(devices["admin"] | devices["viewer"])
        return counts


# --- Login Rate Limiting ---


def check_rate_limit(key: str) -> Tuple[bool, int]:
    """
    Check if a key (e.g. 'ip:1.2.3.4' or 'user:admin') is rate limited.
    Returns (is_allowed: bool, remaining_lockout_seconds: int).
    """
    now = int(time.time())
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT failure_count, locked_until FROM auth_login_attempts WHERE key = ?",
            (key,),
        ).fetchone()
        if not row:
            return True, 0

        locked_until = row["locked_until"]
        if locked_until > now:
            return False, locked_until - now

        return True, 0


def record_failed_attempt(key: str) -> Tuple[bool, int]:
    """
    Record a failed login attempt. Locks out if threshold reached.
    Returns (is_locked: bool, lockout_duration: int).
    """
    now = int(time.time())
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT failure_count, locked_until FROM auth_login_attempts WHERE key = ?", (key,))
        row = cur.fetchone()
        if row:
            locked_until = row["locked_until"]
            if locked_until > now:
                return True, locked_until - now
            new_count = row["failure_count"] + 1
        else:
            new_count = 1

        if new_count >= RATE_LIMIT_MAX_ATTEMPTS:
            new_locked_until = now + RATE_LIMIT_LOCKOUT_SECONDS
            cur.execute(
                """
                INSERT INTO auth_login_attempts (key, failure_count, locked_until, last_attempt)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    failure_count = excluded.failure_count,
                    locked_until = excluded.locked_until,
                    last_attempt = excluded.last_attempt
                """,
                (key, new_count, new_locked_until, now),
            )
            conn.commit()
            return True, RATE_LIMIT_LOCKOUT_SECONDS
        else:
            cur.execute(
                """
                INSERT INTO auth_login_attempts (key, failure_count, locked_until, last_attempt)
                VALUES (?, ?, 0, ?)
                ON CONFLICT(key) DO UPDATE SET
                    failure_count = excluded.failure_count,
                    last_attempt = excluded.last_attempt
                """,
                (key, new_count, now),
            )
            conn.commit()
            return False, 0


def clear_failed_attempts(key: str) -> None:
    """Clear failed login attempts upon successful authentication."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM auth_login_attempts WHERE key = ?", (key,))
        conn.commit()
