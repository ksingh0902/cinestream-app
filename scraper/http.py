"""Polite, browser-like HTTP client with retries, throttling, disk cache, and browser fallback."""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import CRAWL_DELAY, HTTP_TIMEOUT, UA, STREAM_HOST_HINTS


def headers_for(url: str, referer: Optional[str] = None) -> dict:
    """R5: derive Referer/Origin from the host we are actually calling."""
    host = urlparse(url).netloc
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
    if any(k in host for k in STREAM_HOST_HINTS):
        h["Referer"] = f"https://{host}/"
        h["Origin"] = f"https://{host}"
    if referer:
        h["Referer"] = referer
    return h


class HttpClient:
    def __init__(self, delay: float = CRAWL_DELAY, timeout: int = HTTP_TIMEOUT,
                 cache_dir: Optional[str] = ".cache", use_cache: bool = True):
        self.delay, self.timeout, self.use_cache = delay, timeout, use_cache
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.s = requests.Session()
        retry = Retry(total=4, backoff_factor=1.0,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(["GET"]))
        ad = HTTPAdapter(max_retries=retry, pool_maxsize=32)
        self.s.mount("https://", ad)
        self.s.mount("http://", ad)
        self._last = 0.0
        self._playwright = None
        self._browser = None
        self._page = None

    def _cache(self, url: str) -> Optional[Path]:
        return (self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".html")
                if self.cache_dir else None)

    def _browser_get(self, url: str) -> str:
        if self._page is None:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            chrome_path = None
            for p in [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                      r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]:
                if os.path.exists(p):
                    chrome_path = p
                    break
            args = [
                "--disable-blink-features=AutomationControlled",
                "--window-position=-2400,-2400",
                "--window-size=1280,800"
            ]
            self._browser = self._playwright.chromium.launch(
                executable_path=chrome_path, headless=False, args=args
            )
            ctx = self._browser.new_context()
            ctx.on("page", lambda p: p.close())
            self._page = ctx.new_page()

        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
        except Exception:
            pass
        for _ in range(15):
            if "Just a moment" not in self._page.title():
                break
            self._page.wait_for_timeout(500)
        return self._page.content()

    def get(self, url: str, *, referer: Optional[str] = None,
            force: bool = False) -> str:
        cf = self._cache(url)
        if self.use_cache and cf and cf.exists() and not force:
            return cf.read_text(encoding="utf-8", errors="ignore")

        gap = time.time() - self._last
        if gap < self.delay:
            time.sleep(self.delay - gap)

        text = None
        if "yomovies.wine" in url:
            text = self._browser_get(url)
        else:
            try:
                r = self.s.get(url, headers=headers_for(url, referer), timeout=self.timeout)
                if r.status_code == 403:
                    raise requests.HTTPError(response=r)
                r.raise_for_status()
                r.encoding = r.apparent_encoding or "utf-8"
                text = r.text
            except Exception as e:
                try:
                    text = self._browser_get(url)
                except Exception:
                    raise e

        self._last = time.time()
        if self.use_cache and cf and text:
            cf.write_text(text, encoding="utf-8")
        return text

    def close(self):
        self.s.close()
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
            self._page = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def __enter__(self): return self
    def __exit__(self, *a): self.close()
