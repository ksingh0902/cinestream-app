"""Persistent storage for TV devices, short-lived pairing sessions, and authorized phone controllers.

Uses the shared Auth/App State database (Postgres in production, SQLite in local dev)
via app.auth.database.connect(). Never touches the read-only catalogue DB or existing auth_* tables.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.auth.database import connect as get_db_connection

logger = logging.getLogger("cinemymovies.tv.store")

TV_DDL_STATEMENTS = """
CREATE TABLE IF NOT EXISTS tv_devices (
    tv_id TEXT PRIMARY KEY,
    owner_username TEXT NOT NULL,
    name TEXT NOT NULL,
    device_secret_hash TEXT NOT NULL,
    last_ip_hash TEXT,
    last_seen_at BIGINT NOT NULL,
    created_at BIGINT NOT NULL,
    revoked_at BIGINT
);

CREATE INDEX IF NOT EXISTS idx_tv_devices_owner ON tv_devices(owner_username);
CREATE INDEX IF NOT EXISTS idx_tv_devices_ip ON tv_devices(last_ip_hash);

CREATE TABLE IF NOT EXISTS tv_pairing_sessions (
    pairing_id TEXT PRIMARY KEY,
    tv_id TEXT NOT NULL,
    owner_username TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at BIGINT NOT NULL,
    consumed_at BIGINT,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tv_pairing_tv ON tv_pairing_sessions(tv_id);
CREATE INDEX IF NOT EXISTS idx_tv_pairing_owner_code ON tv_pairing_sessions(owner_username, code_hash);
CREATE INDEX IF NOT EXISTS idx_tv_pairing_expires ON tv_pairing_sessions(expires_at);

CREATE TABLE IF NOT EXISTS tv_authorized_controllers (
    controller_id TEXT PRIMARY KEY,
    tv_id TEXT NOT NULL,
    owner_username TEXT NOT NULL,
    phone_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'primary',
    control_token_hash TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    last_seen_at BIGINT NOT NULL,
    revoked_at BIGINT
);

CREATE INDEX IF NOT EXISTS idx_tv_controllers_tv ON tv_authorized_controllers(tv_id);
CREATE INDEX IF NOT EXISTS idx_tv_controllers_owner ON tv_authorized_controllers(owner_username);
"""


def init_tv_db() -> None:
    """Create TV pairing & controller tables if they do not exist."""
    try:
        with get_db_connection() as conn:
            conn.executescript(TV_DDL_STATEMENTS)
    except Exception:
        logger.exception("Failed to initialize TV pairing database tables")


def _row_to_dict(row: Any) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return dict(row)


def upsert_tv_device(
    *,
    tv_id: str,
    owner_username: str,
    name: str,
    device_secret_hash: str,
    ip_hash: Optional[str],
    now: Optional[int] = None,
) -> Dict[str, Any]:
    ts = int(now if now is not None else time.time())
    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM tv_devices WHERE tv_id = ?", (tv_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE tv_devices
                SET name = ?, device_secret_hash = ?, last_ip_hash = ?, last_seen_at = ?, revoked_at = NULL
                WHERE tv_id = ? AND owner_username = ?
                """,
                (name, device_secret_hash, ip_hash, ts, tv_id, owner_username),
            )
        else:
            conn.execute(
                """
                INSERT INTO tv_devices (
                    tv_id, owner_username, name, device_secret_hash,
                    last_ip_hash, last_seen_at, created_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (tv_id, owner_username, name, device_secret_hash, ip_hash, ts, ts),
            )
        row = conn.execute("SELECT * FROM tv_devices WHERE tv_id = ?", (tv_id,)).fetchone()
        return dict(row)


def get_tv_device(tv_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM tv_devices WHERE tv_id = ?", (tv_id,)).fetchone()
        return _row_to_dict(row)


def list_tv_devices_for_user(owner_username: str) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tv_devices
            WHERE owner_username = ? AND revoked_at IS NULL
            ORDER BY last_seen_at DESC, created_at DESC
            """,
            (owner_username,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_tv_presence(tv_id: str, ip_hash: Optional[str], now: Optional[int] = None) -> None:
    ts = int(now if now is not None else time.time())
    with get_db_connection() as conn:
        if ip_hash is not None:
            conn.execute(
                "UPDATE tv_devices SET last_seen_at = ?, last_ip_hash = ? WHERE tv_id = ? AND revoked_at IS NULL",
                (ts, ip_hash, tv_id),
            )
        else:
            conn.execute(
                "UPDATE tv_devices SET last_seen_at = ? WHERE tv_id = ? AND revoked_at IS NULL",
                (ts, tv_id),
            )


def revoke_tv_device(tv_id: str, owner_username: str, now: Optional[int] = None) -> bool:
    ts = int(now if now is not None else time.time())
    with get_db_connection() as conn:
        cur = conn.execute(
            "UPDATE tv_devices SET revoked_at = ? WHERE tv_id = ? AND owner_username = ? AND revoked_at IS NULL",
            (ts, tv_id, owner_username),
        )
        conn.execute(
            "UPDATE tv_authorized_controllers SET revoked_at = ? WHERE tv_id = ? AND owner_username = ? AND revoked_at IS NULL",
            (ts, tv_id, owner_username),
        )
        conn.execute(
            "UPDATE tv_pairing_sessions SET consumed_at = ? WHERE tv_id = ? AND owner_username = ? AND consumed_at IS NULL",
            (ts, tv_id, owner_username),
        )
        return cur.rowcount > 0


def create_pairing_session(
    *,
    pairing_id: str,
    tv_id: str,
    owner_username: str,
    code_hash: str,
    token_hash: str,
    expires_at: int,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    ts = int(now if now is not None else time.time())
    with get_db_connection() as conn:
        # Invalidate any previous unconsumed pairing sessions for this TV
        conn.execute(
            "UPDATE tv_pairing_sessions SET consumed_at = ? WHERE tv_id = ? AND consumed_at IS NULL",
            (ts, tv_id),
        )
        conn.execute(
            """
            INSERT INTO tv_pairing_sessions (
                pairing_id, tv_id, owner_username, code_hash, token_hash,
                expires_at, consumed_at, failed_attempts, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, 0, ?)
            """,
            (pairing_id, tv_id, owner_username, code_hash, token_hash, int(expires_at), ts),
        )
        row = conn.execute(
            "SELECT * FROM tv_pairing_sessions WHERE pairing_id = ?", (pairing_id,)
        ).fetchone()
        return dict(row)


def get_pairing_session_by_id(pairing_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM tv_pairing_sessions WHERE pairing_id = ?", (pairing_id,)
        ).fetchone()
        return _row_to_dict(row)


def list_recent_pairing_sessions_for_user(owner_username: str, now: Optional[int] = None) -> List[Dict[str, Any]]:
    ts = int(now if now is not None else time.time())
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tv_pairing_sessions
            WHERE owner_username = ? AND consumed_at IS NULL AND expires_at >= ?
            ORDER BY created_at DESC
            """,
            (owner_username, ts),
        ).fetchall()
        return [dict(r) for r in rows]


def increment_pairing_failed_attempts(pairing_id: str) -> int:
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE tv_pairing_sessions SET failed_attempts = failed_attempts + 1 WHERE pairing_id = ?",
            (pairing_id,),
        )
        row = conn.execute(
            "SELECT failed_attempts FROM tv_pairing_sessions WHERE pairing_id = ?",
            (pairing_id,),
        ).fetchone()
        return int(row["failed_attempts"]) if row else 0


def consume_pairing_session(pairing_id: str, now: Optional[int] = None) -> bool:
    """Atomically mark a pairing session as consumed. Returns True only on first consumption."""
    ts = int(now if now is not None else time.time())
    with get_db_connection() as conn:
        cur = conn.execute(
            "UPDATE tv_pairing_sessions SET consumed_at = ? WHERE pairing_id = ? AND consumed_at IS NULL",
            (ts, pairing_id),
        )
        return cur.rowcount == 1


def create_authorized_controller(
    *,
    controller_id: str,
    tv_id: str,
    owner_username: str,
    phone_name: str,
    role: str,
    control_token_hash: str,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    ts = int(now if now is not None else time.time())
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO tv_authorized_controllers (
                controller_id, tv_id, owner_username, phone_name, role,
                control_token_hash, created_at, last_seen_at, revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (controller_id, tv_id, owner_username, phone_name, role, control_token_hash, ts, ts),
        )
        row = conn.execute(
            "SELECT * FROM tv_authorized_controllers WHERE controller_id = ?",
            (controller_id,),
        ).fetchone()
        return dict(row)


def list_active_controllers_for_tv(tv_id: str) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tv_authorized_controllers
            WHERE tv_id = ? AND revoked_at IS NULL
            ORDER BY created_at ASC
            """,
            (tv_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_controller(controller_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM tv_authorized_controllers WHERE controller_id = ?",
            (controller_id,),
        ).fetchone()
        return _row_to_dict(row)


def touch_controller(controller_id: str, now: Optional[int] = None) -> None:
    ts = int(now if now is not None else time.time())
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE tv_authorized_controllers SET last_seen_at = ? WHERE controller_id = ? AND revoked_at IS NULL",
            (ts, controller_id),
        )


def revoke_controller(controller_id: str, owner_username: str, now: Optional[int] = None) -> bool:
    ts = int(now if now is not None else time.time())
    with get_db_connection() as conn:
        cur = conn.execute(
            """
            UPDATE tv_authorized_controllers
            SET revoked_at = ?
            WHERE controller_id = ? AND owner_username = ? AND revoked_at IS NULL
            """,
            (ts, controller_id, owner_username),
        )
        return cur.rowcount > 0


def revoke_all_controllers_for_tv(tv_id: str, owner_username: str, now: Optional[int] = None) -> int:
    ts = int(now if now is not None else time.time())
    with get_db_connection() as conn:
        cur = conn.execute(
            """
            UPDATE tv_authorized_controllers
            SET revoked_at = ?
            WHERE tv_id = ? AND owner_username = ? AND revoked_at IS NULL
            """,
            (ts, tv_id, owner_username),
        )
        return int(cur.rowcount or 0)
