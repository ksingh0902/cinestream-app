from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from config import DB_PATH

logger = logging.getLogger("cinemymovies.auth")

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# Secret key for HMAC cookie signing.
# If not provided, a random 32-byte secret is used for the current process lifetime.
_raw_secret = os.getenv("SESSION_SECRET", "")
if not _raw_secret:
    if IS_PRODUCTION:
        logger.warning(
            "CRITICAL: SESSION_SECRET is not set in production! "
            "Please set SESSION_SECRET in your environment variables to persist sessions across restarts."
        )
    SESSION_SECRET = secrets.token_hex(32)
else:
    SESSION_SECRET = _raw_secret

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip()
ADMIN_INITIAL_PASSWORD = (os.getenv("ADMIN_INITIAL_PASSWORD") or os.getenv("ADMIN_PASSWORD") or "").strip()

VIEWER_USERNAME = os.getenv("VIEWER_USERNAME", "viewer").strip()
VIEWER_INITIAL_PASSWORD = (os.getenv("VIEWER_INITIAL_PASSWORD") or os.getenv("VIEWER_PASSWORD") or "").strip()

SESSION_COOKIE_NAME = "cms_session"
CSRF_COOKIE_NAME = "cms_csrf"
SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS", "604800"))  # 7 days

# Persistent storage database resolution
def resolve_auth_db_path() -> str:
    """Resolve durable database path, auto-detecting Render persistent disks or environment configs."""
    custom = os.getenv("AUTH_DB_PATH", "").strip()
    if custom:
        return custom

    # Check standard Render / Linux persistent volume mount points
    for mount_dir in ("/var/data", "/data", os.getenv("PERSISTENT_DATA_DIR", "").strip()):
        if mount_dir and os.path.exists(mount_dir) and os.access(mount_dir, os.W_OK):
            target = os.path.join(mount_dir, "cinemymovies.sqlite3")
            logger.info("Using persistent volume mount for auth database: %s", target)
            return target

    if os.path.exists("cinemymovies.sqlite3"):
        return "cinemymovies.sqlite3"
    return DB_PATH or "cinemymovies.sqlite3"

AUTH_DB_PATH = resolve_auth_db_path()

def get_setup_lockfile_path() -> Path:
    """Path to the persistent lock marker indicating initial setup has completed."""
    db_p = Path(AUTH_DB_PATH)
    try:
        return db_p.parent / ".setup_locked"
    except Exception:
        return Path(".setup_locked")

# Login rate limiting parameters: 5 failed attempts locks for 5 minutes (300 seconds)
RATE_LIMIT_MAX_ATTEMPTS = int(os.getenv("RATE_LIMIT_MAX_ATTEMPTS", "5"))
RATE_LIMIT_LOCKOUT_SECONDS = int(os.getenv("RATE_LIMIT_LOCKOUT_SECONDS", "300"))
