"""Central config. Everything overridable by env var."""
import os

# --- upstream site (R3: list of mirrors, first healthy one wins) ---
SITE_MIRRORS = [m.strip().rstrip("/") for m in os.getenv(
    "SITE_MIRRORS", "https://yomovies.exchange,https://yomovies.wine").split(",") if m.strip()]

# fallback only used if the page gives us no absolute embed URL
DEFAULT_EMBED_HOST = os.getenv("DEFAULT_EMBED_HOST", "https://speedostream1.com")

# --- timing ---
STREAM_TTL   = int(os.getenv("STREAM_TTL", "1800"))     # 30 min  (< 6h, R2)
CRAWL_DELAY  = float(os.getenv("CRAWL_DELAY", "0.6"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "25"))

DB_PATH = os.getenv("DB_PATH", "yomovies.db" if os.path.exists("yomovies.db") else "cinemymovies.sqlite3")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

# hosts that need a player-page Referer to avoid 403 (R5)
STREAM_HOST_HINTS = ("speedostream", "ydc1wes", "ydc1", "ygsmn", "vsyshost")
