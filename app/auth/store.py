from __future__ import annotations

import logging
import sqlite3
import time
from enum import Enum
from pathlib import Path
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


def get_db_connection() -> sqlite3.Connection:
    """Connect to SQLite database with WAL journal mode, busy timeout, and row_factory."""
    db_path = getattr(config, "AUTH_DB_PATH", None) or "cinemymovies.sqlite3"
    p = Path(db_path)
    if not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=30.0)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def write_setup_lockfile() -> None:
    """Write persistent setup lockfile to disk."""
    try:
        lock_path = get_setup_lockfile_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(f"setup_locked_at={int(time.time())}\n", encoding="utf-8")
    except Exception as e:
        logger.warning("Could not write setup lockfile: %s", e)


def has_setup_lockfile() -> bool:
    """Check if the persistent setup lockfile exists."""
    try:
        return get_setup_lockfile_path().exists()
    except Exception:
        return False


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
    """
    Evaluate the global authentication system status:
    1. STORAGE_UNAVAILABLE: Database connection or query failed due to I/O, lock, or disk failure.
    2. INITIALIZED: Setup has already been completed, OR valid credentials exist in DB, OR bootstrap env vars are present.
    3. GENUINELY_UNINITIALIZED: Storage is healthy, but no users exist, setup has not been performed, and no credentials in env.
    """
    try:
        with get_db_connection() as conn:
            conn.executescript(DDL_STATEMENTS)

            # 1. Check for explicit setup_completed flag in auth_meta
            row_meta = conn.execute("SELECT value FROM auth_meta WHERE key = 'setup_completed'").fetchone()
            is_meta_completed = row_meta and row_meta["value"] == "1"

            # 2. Check existing user credentials
            admin_user = conn.execute("SELECT username, password_hash FROM auth_users WHERE role = 'admin' LIMIT 1").fetchone()
            viewer_user = conn.execute("SELECT username, password_hash FROM auth_users WHERE role = 'viewer' LIMIT 1").fetchone()

            has_valid_admin = bool(admin_user and admin_user["password_hash"])
            has_valid_viewer = bool(viewer_user and viewer_user["password_hash"])

            # If users already exist in DB, heal and enforce INITIALIZED state
            if has_valid_admin or is_meta_completed:
                if not is_meta_completed and has_valid_admin:
                    set_meta_value(conn, "setup_completed", "1")
                    conn.commit()
                    logger.info("Auto-healed setup_completed flag from existing admin user.")
                if not has_setup_lockfile():
                    write_setup_lockfile()
                return AuthSystemState.INITIALIZED, None

            # 3. If environment credentials provided, bootstrap and return INITIALIZED
            if ADMIN_INITIAL_PASSWORD or VIEWER_INITIAL_PASSWORD:
                init_auth_db()
                return AuthSystemState.INITIALIZED, None

            # 4. Check if setup lockfile exists on disk
            if has_setup_lockfile():
                set_meta_value(conn, "setup_completed", "1")
                conn.commit()
                return AuthSystemState.INITIALIZED, None

            # 5. Genuine first-time uninitialized
            return AuthSystemState.GENUINELY_UNINITIALIZED, None

    except (sqlite3.Error, OSError, Exception) as e:
        logger.error("Auth storage failure during state check: %s", e)
        return AuthSystemState.STORAGE_UNAVAILABLE, str(e)


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
    state, err = get_auth_system_state()
    if state == AuthSystemState.STORAGE_UNAVAILABLE:
        return False, f"Authentication storage is currently unavailable: {err}"
    if state == AuthSystemState.INITIALIZED:
        return False, "Initial setup has already been completed and is permanently locked."

    if not admin_password or len(admin_password) < 8:
        return False, "Administrator password must be at least 8 characters long."

    if not viewer_password or len(viewer_password) < 6:
        return False, "Shared viewer password must be at least 6 characters long."

    now = int(time.time())
    admin_hash = hash_password(admin_password)
    viewer_hash = hash_password(viewer_password)

    try:
        with get_db_connection() as conn:
            # Check atomically inside transaction if any user exists
            existing_count = conn.execute("SELECT COUNT(*) FROM auth_users WHERE role IN ('admin', 'viewer')").fetchone()[0]
            if existing_count > 0:
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
        return False, f"Failed to save credentials: {e}"


def init_auth_db() -> None:
    """Initialize auth tables and bootstrap initial credentials if provided in env, preserving existing credentials."""
    try:
        with get_db_connection() as conn:
            conn.executescript(DDL_STATEMENTS)
            conn.commit()

            now = int(time.time())

            # Check if admin already exists
            existing_admin = conn.execute("SELECT username, password_hash FROM auth_users WHERE role = 'admin' LIMIT 1").fetchone()
            if not existing_admin and ADMIN_INITIAL_PASSWORD:
                admin_hash = hash_password(ADMIN_INITIAL_PASSWORD)
                conn.execute(
                    """
                    INSERT INTO auth_users (username, password_hash, role, auth_version, created_at, updated_at)
                    VALUES (?, ?, 'admin', 1, ?, ?)
                    ON CONFLICT(username) DO NOTHING
                    """,
                    (ADMIN_USERNAME, admin_hash, now, now),
                )
                set_meta_value(conn, "setup_completed", "1")
                conn.execute("DELETE FROM auth_login_attempts")
                logger.info("Administrator account initialized from ADMIN_INITIAL_PASSWORD.")
            elif existing_admin:
                # Existing credentials preserved; ensure setup_completed is marked
                set_meta_value(conn, "setup_completed", "1")

            # Check if viewer already exists
            existing_viewer = conn.execute("SELECT username, password_hash FROM auth_users WHERE role = 'viewer' LIMIT 1").fetchone()
            if not existing_viewer and VIEWER_INITIAL_PASSWORD:
                viewer_hash = hash_password(VIEWER_INITIAL_PASSWORD)
                conn.execute(
                    """
                    INSERT INTO auth_users (username, password_hash, role, auth_version, created_at, updated_at)
                    VALUES (?, ?, 'viewer', 1, ?, ?)
                    ON CONFLICT(username) DO NOTHING
                    """,
                    (VIEWER_USERNAME, viewer_hash, now, now),
                )
                logger.info("Shared viewer account initialized from VIEWER_INITIAL_PASSWORD.")

            conn.commit()
            if existing_admin or ADMIN_INITIAL_PASSWORD:
                write_setup_lockfile()
    except Exception as e:
        logger.error("Error during init_auth_db: %s", e)


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


def count_active_sessions() -> Dict[str, int]:
    """Count active unexpired sessions by role."""
    now = int(time.time())
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT role, COUNT(*) as cnt FROM auth_sessions WHERE expires_at >= ? GROUP BY role", (now,))
        counts = {"admin": 0, "viewer": 0, "total": 0}
        for r in cur.fetchall():
            counts[r["role"]] = r["cnt"]
            counts["total"] += r["cnt"]
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
