from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Movies7Config:
    homepage: str = "https://movies7to.net/home/"
    origin: str = "https://movies7to.net"
    tmdb_keys: list[str] = field(default_factory=lambda: [
        "abbf502ad7ef5458bf0b91e09d5043c0",
        "15d2ea6d0dc1d476efbca3eba2b9bbfb",
        "d0e6107be30f2a3cb0a34ad2a90ceb6f",
    ])
    tmdb_hosts: list[str] = field(default_factory=lambda: [
        "api.tmdb.org",
        "api.themoviedb.org",
    ])
    timeout_s: float = 10.0


CFG = Movies7Config()
