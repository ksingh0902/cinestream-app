from __future__ import annotations

import hashlib
import random
import re
import threading

from .http import get, session

_TOKEN_RE = re.compile(r"^[0-9a-f]{32}")
_lock = threading.Lock()
_verified: set[str] = set()


def _solve(seed: str, bits: int, limit: int = 25_000_000) -> int:
    target = 1 << (32 - bits)
    n = 0
    while n < limit:
        n += 1
        digest = hashlib.sha256(f"{seed}:{n}".encode()).digest()
        if int.from_bytes(digest[:4], "big") < target:
            return n
    raise RuntimeError(f"PoW exhausted (seed={seed!r} bits={bits})")


def _rand() -> str:
    return "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789")
                   for _ in range(8))


def verify(base: str, path: str, *, force: bool = False) -> bool:
    """Ensure the session holds a valid gate cookie for `base`. Idempotent."""
    key = f"{base}{path}"
    with _lock:
        if not force and key in _verified:
            return True

    host = base.split("//", 1)[-1].split("/")[0]
    s = session()
    s.cookies.set("hv", "1", domain=host)
    s.cookies.set("hv2", "1", domain=host)

    seed = bits = None
    try:
        r = get(base + path, params={"__hvtok": "1", "s": "1", "r": "0"},
                accept="*/*")
        if "json" in r.headers.get("Content-Type", ""):
            payload = r.json()
            seed, bits = payload.get("seed"), int(payload.get("bits") or 0)
    except Exception:
        pass

    if seed and bits:
        n = _solve(seed, bits)
        body = get(base + path,
                   params={"__hvtok": "1", "seed": seed, "n": n,
                           "r": "0", "z": _rand()},
                   accept="*/*").text.strip()
    else:
        body = get(base + path,
                   params={"__hvtok": "1", "nc": "1", "r": "0", "z": _rand()},
                   accept="*/*").text.strip()

    ok = bool(_TOKEN_RE.match(body))
    with _lock:
        if ok:
            _verified.add(key)
        else:
            _verified.discard(key)
    return ok


def invalidate(base: str, path: str) -> None:
    with _lock:
        _verified.discard(f"{base}{path}")
