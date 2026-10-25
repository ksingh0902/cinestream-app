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

# Persistent storage database
AUTH_DB_PATH = os.getenv("AUTH_DB_PATH", DB_PATH or "cinemymovies.sqlite3")

# Login rate limiting parameters: 5 failed attempts locks for 5 minutes (300 seconds)
RATE_LIMIT_MAX_ATTEMPTS = int(os.getenv("RATE_LIMIT_MAX_ATTEMPTS", "5"))
RATE_LIMIT_LOCKOUT_SECONDS = int(os.getenv("RATE_LIMIT_LOCKOUT_SECONDS", "300"))
