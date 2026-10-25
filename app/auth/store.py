from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    ADMIN_INITIAL_PASSWORD,
    ADMIN_USERNAME,
    AUTH_DB_PATH,
    RATE_LIMIT_LOCKOUT_SECONDS,
    RATE_LIMIT_MAX_ATTEMPTS,
    VIEWER_INITIAL_PASSWORD,
    VIEWER_USERNAME,
)
from .security import hash_password

logger = logging.getLogger("cinemymovies.auth.store")

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
    """Connect to SQLite database with WAL journal mode and row_factory."""
    db_path = AUTH_DB_PATH or "cinemymovies.sqlite3"
    p = Path(db_path)
    if not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


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


def is_setup_completed() -> bool:
    """Check if initial setup has been completed."""
    val = get_meta_value("setup_completed")
    return val == "1"


def complete_initial_setup(
    admin_password: str,
    viewer_password: str,
    admin_username: str = ADMIN_USERNAME,
    viewer_username: str = VIEWER_USERNAME,
) -> Tuple[bool, Optional[str]]:
    """Complete initial setup by setting admin and viewer passwords."""
    if is_setup_completed():
        return False, "Initial setup has already been completed."

    if not admin_password or len(admin_password) < 8:
        return False, "Administrator password must be at least 8 characters long."

    if not viewer_password or len(viewer_password) < 6:
        return False, "Shared viewer password must be at least 6 characters long."

    now = int(time.time())
    admin_hash = hash_password(admin_password)
    viewer_hash = hash_password(viewer_password)

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO auth_users (username, password_hash, role, auth_version, created_at, updated_at)
            VALUES (?, ?, 'admin', 1, ?, ?)
            ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash, updated_at = excluded.updated_at
            """,
            (admin_username.strip() or "admin", admin_hash, now, now),
        )
        conn.execute(
            """
            INSERT INTO auth_users (username, password_hash, role, auth_version, created_at, updated_at)
            VALUES (?, ?, 'viewer', 1, ?, ?)
            ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash, updated_at = excluded.updated_at
            """,
            (viewer_username.strip() or "viewer", viewer_hash, now, now),
        )
        set_meta_value(conn, "setup_completed", "1")
        conn.execute("DELETE FROM auth_login_attempts")
        conn.commit()

    logger.info("Initial setup completed successfully for admin and viewer.")
    return True, None


def init_auth_db() -> None:
    """Initialize auth tables and bootstrap initial credentials if provided in env."""
    with get_db_connection() as conn:
        conn.executescript(DDL_STATEMENTS)
        conn.commit()

        now = int(time.time())

        # If environment variables provide credentials, configure them automatically
        if ADMIN_INITIAL_PASSWORD:
            admin_hash = hash_password(ADMIN_INITIAL_PASSWORD)
            conn.execute(
                """
                INSERT INTO auth_users (username, password_hash, role, auth_version, created_at, updated_at)
                VALUES (?, ?, 'admin', 1, ?, ?)
                ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash, updated_at = excluded.updated_at
                """,
                (ADMIN_USERNAME, admin_hash, now, now),
            )
            set_meta_value(conn, "setup_completed", "1")
            conn.execute("DELETE FROM auth_login_attempts")
            logger.info("Administrator account initialized/synced from ADMIN_INITIAL_PASSWORD.")

        if VIEWER_INITIAL_PASSWORD:
            viewer_hash = hash_password(VIEWER_INITIAL_PASSWORD)
            conn.execute(
                """
                INSERT INTO auth_users (username, password_hash, role, auth_version, created_at, updated_at)
                VALUES (?, ?, 'viewer', 1, ?, ?)
                ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash, updated_at = excluded.updated_at
                """,
                (VIEWER_USERNAME, viewer_hash, now, now),
            )
            logger.info("Shared viewer account initialized/synced from VIEWER_INITIAL_PASSWORD.")

        conn.commit()


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
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE auth_users
            SET password_hash = ?, auth_version = auth_version + 1, updated_at = ?
            WHERE username = ?
            """,
            (new_hash, now, username),
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
