"""Polite, retrying, thread-local session factory."""
from __future__ import annotations

import random
import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import CFG

_local = threading.local()


def session() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": CFG.user_agent,
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        })
        retry = Retry(
            total=4, backoff_factor=0.7, respect_retry_after_header=True,
            status_forcelist=(408, 429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "HEAD"]),
        )
        adapter = HTTPAdapter(max_retries=retry,
                              pool_connections=CFG.workers * 2,
                              pool_maxsize=CFG.workers * 2)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _local.s = s
    return s


def get(url: str, *, params=None, accept: str = "text/html",
        headers: dict | None = None) -> requests.Response:
    time.sleep(CFG.delay * (0.6 + random.random() * 0.8))
    h = {"Accept": accept}
    if headers:
        h.update(headers)
    r = session().get(url, params=params, headers=h, timeout=CFG.timeout)
    r.raise_for_status()
    return r
