"""CINEMY TV Remote — Pairing, Device Registry, and Realtime Control."""
from .routes import tv_router
from .store import init_tv_db

__all__ = ["tv_router", "init_tv_db"]
