import os
from dataclasses import dataclass, field

def _list(name: str, default: str) -> list[str]:
    return [h.strip() for h in os.getenv(name, default).split(",") if h.strip()]

@dataclass
class Config:
    # --- catalogue (metadata only, no player) ---
    catalog_mirrors: list[str] = field(
        default_factory=lambda: _list("A4M_MIRRORS", "https://ask4movietv.cyou"))
    # --- streaming host (has the player) ---
    stream_mirrors: list[str] = field(
        default_factory=lambda: _list("FBOX_MIRRORS", "https://flixfever.cyou,https://fbox.gd"))

    db_path: str = os.getenv("DB_PATH", "cinemymovies.sqlite3" if os.path.exists("cinemymovies.sqlite3") else "yomovies.db")
    delay: float = float(os.getenv("CRAWL_DELAY", "0.6"))
    workers: int = int(os.getenv("CRAWL_WORKERS", "4"))
    timeout: int = int(os.getenv("HTTP_TIMEOUT", "25"))
    user_agent: str = os.getenv(
        "CRAWL_UA",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    )
    tmdb_api_key: str = os.getenv("TMDB_API_KEY", "")
    player_ttl_s: int = int(os.getenv("PLAYER_TTL_S", str(6 * 3600)))
    debug_dump: str = os.getenv("A4M_DEBUG_DUMP", "")

CFG = Config()
