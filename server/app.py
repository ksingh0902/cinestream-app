"""Backend: catalogue + self-healing stream resolver + CORS-proof HLS proxy."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from config import DB_PATH, STREAM_TTL, UA, SITE_MIRRORS
from scraper.extract import parse_detail, EMBED_RE
from scraper.http import HttpClient, headers_for
from scraper.resolve import StreamResolver
from scraper.store import connect
from app.api import catalog_router, stream_router
from app.auth.routes import auth_router
from app.auth.middleware import PrivateAccessMiddleware
from app.auth.store import init_auth_db

import asyncio
import os

app = FastAPI(title="CineMyMovies API")
app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(stream_router)

app.add_middleware(PrivateAccessMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_sync_task: Optional[asyncio.Task] = None

async def _periodic_sync_loop():
    """Background task that runs on server startup and every 12 hours (daily/bidaily) to fetch newly added movies."""
    await asyncio.sleep(5)
    while True:
        try:
            print("[auto-sync] Running scheduled catalog sync...", flush=True)
            from app.sync import run_full_sync
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, run_full_sync)
            print(f"[auto-sync] Scheduled sync finished: {result}", flush=True)
        except Exception as exc:
            print(f"[auto-sync] Error during scheduled sync: {exc}", flush=True)

        interval_hours = float(os.getenv("SYNC_INTERVAL_HOURS", "12"))
        await asyncio.sleep(max(1.0, interval_hours) * 3600)

@app.on_event("startup")
async def startup_sync_scheduler():
    init_auth_db()
    # Fast startup: do not block boot or burn CPU with heavy multi-view prewarming.
    # Cache warming is handled lazily on-demand per user request.
    global _sync_task
    # Production web workers must strictly serve traffic. Background scraping is decoupled.
    if os.getenv("ENABLE_AUTO_SYNC", "0") == "1" and os.getenv("DISABLE_AUTO_SYNC", "0") != "1":
        _sync_task = asyncio.create_task(_periodic_sync_loop())

@app.on_event("shutdown")
async def shutdown_sync_scheduler():
    global _sync_task
    if _sync_task:
        _sync_task.cancel()

@app.post("/api/sync/latest")
async def trigger_sync():
    """Development-only manual sync; production imports run outside the API VM."""
    if os.getenv("ENVIRONMENT", "").lower() == "production" or os.getenv("DISABLE_AUTO_SYNC", "0") == "1":
        raise HTTPException(409, "Catalogue sync is disabled in the production API container")
    from app.sync import run_full_sync
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_full_sync)
    return result

@app.get("/api/sync/status")
def sync_status():
    """Check last sync status and timestamp."""
    from app.sync import get_sync_status
    return get_sync_status()

@app.middleware("http")
async def add_no_cache_for_html(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in ("/", "/index.html") or response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

_http = HttpClient(delay=0.0, cache_dir=".cache")
_resolver = StreamResolver(_http)
_client = httpx.AsyncClient(timeout=30, follow_redirects=True)


def db():
    p = Path(DB_PATH)
    if not p.exists():
        raise HTTPException(500, "run run_crawl.py first")
    return connect(str(p))


def _row(r) -> dict:
    d = dict(r)
    for k in ("genres", "actors", "director", "country", "embeds", "downloads"):
        d[k] = json.loads(d.get(k) or "[]")
    return d


ADULT_EXCLUSION_SQL = (
    "(genres NOT LIKE '%\"Erotic Movies\"%' OR genres IS NULL) "
    "AND (genres NOT LIKE '%\"Erotic\"%' OR genres IS NULL) "
    "AND (genres NOT LIKE '%\"Hot Series\"%' OR genres IS NULL) "
    "AND (url NOT LIKE '%/genre/erotic-movies/%' OR url IS NULL) "
    "AND (url NOT LIKE '%/genre/hot-series/%' OR url IS NULL) "
    "AND (url NOT LIKE '%/hot-series/%' OR url IS NULL) "
    "AND title NOT LIKE '%Erotic%' "
    "AND title NOT LIKE '%Hot Series%' "
    "AND title NOT LIKE '%Hot Web Series%' "
    "AND title NOT LIKE '%Ullu%' "
    "AND title NOT LIKE '%Altbalaji%' "
    "AND title NOT LIKE '%Alt Balaji%' "
    "AND title NOT LIKE '%WOOW%' "
    "AND title NOT LIKE '%PrimePlay%' "
    "AND title NOT LIKE '%Prime Play%' "
    "AND title NOT LIKE '%Nuefliks%' "
    "AND title NOT LIKE '%MoodX%' "
    "AND title NOT LIKE '%Besharams%' "
    "AND title NOT LIKE '%Feneomovies%' "
    "AND title NOT LIKE '%Feneo%' "
    "AND title NOT LIKE '%Gemplex%' "
    "AND title NOT LIKE '%BoomMovies%' "
    "AND title NOT LIKE '%Boom Movies%' "
    "AND title NOT LIKE '%Night Show%' "
    "AND title NOT LIKE '%Hootzy%' "
    "AND title NOT LIKE '%Bambooflix%' "
    "AND title NOT LIKE '%Eightshots%' "
    "AND title NOT LIKE '%Eight Shots%' "
    "AND title NOT LIKE '%BananaPrime%' "
    "AND title NOT LIKE '%Banana Prime%' "
    "AND title NOT LIKE '%Chikooflix%' "
    "AND title NOT LIKE '%Cinemadosti%' "
    "AND title NOT LIKE '%CliffMovies%' "
    "AND title NOT LIKE '%Flixsksmovies%' "
    "AND title NOT LIKE '%Balloons%' "
    "AND title NOT LIKE '%Piliflix%' "
    "AND title NOT LIKE '%I-Entertainment%' "
    "AND title NOT LIKE '%HotHit%' "
    "AND title NOT LIKE '%Glamheart%' "
    "AND title NOT LIKE '%Fliz Movies%' "
    "AND title NOT LIKE '%FlizMovies%' "
    "AND title NOT LIKE '%(Fliz%' "
    "AND title NOT LIKE '% Fliz%' "
    "AND title NOT LIKE '%(Hunters%' "
    "AND title NOT LIKE '%Hunters Original%' "
    "AND title NOT LIKE '%Hunters App%' "
    "AND title NOT LIKE '%Gupchup%' "
    "AND title NOT LIKE '%Primeflix%' "
    "AND title NOT LIKE '%HotMasti%' "
    "AND title NOT LIKE '%MastiPrime%' "
    "AND title NOT LIKE '%Lootlo%' "
    "AND title NOT LIKE '%Big Movie Zoo%' "
    "AND title NOT LIKE '%11upmovies%' "
    "AND title NOT LIKE '%Hotprime%' "
    "AND title NOT LIKE '%Worldprime%' "
    "AND title NOT LIKE '%PrimeShots%' "
    "AND title NOT LIKE '%Prime Shots%' "
    "AND title NOT LIKE '%Hotshots%' "
    "AND title NOT LIKE '%HotX%' "
    "AND title NOT LIKE '%VooVi%' "
    "AND title NOT LIKE '%Voovi%' "
    "AND title NOT LIKE '%Kooku%' "
    "AND title NOT LIKE '%(Rabbit%' "
    "AND title NOT LIKE '%Rabbit Original%' "
    "AND title NOT LIKE '%Rabbit Movies%' "
    "AND title NOT LIKE '%Cineprime%' "
    "AND title NOT LIKE '%Cine Prime%' "
    "AND title NOT LIKE '%RedPrime%' "
    "AND title NOT LIKE '%Red Prime%' "
    "AND title NOT LIKE '%Feelit%' "
    "AND title NOT LIKE '%Yessma%' "
    "AND title NOT LIKE '%Jalva%' "
    "AND title NOT LIKE '%HuntCinema%' "
    "AND title NOT LIKE '%Mastiplay%' "
    "AND title NOT LIKE '%BulbulPlay%' "
    "AND title NOT LIKE '%Kaddu%' "
    "AND title NOT LIKE '%DesiPrime%' "
    "AND title NOT LIKE '%Atrangii%' "
    "AND title NOT LIKE '%Jugnutv%' "
    "AND title NOT LIKE '%Honeymoon Couples%' "
    "AND title NOT LIKE '%Tempt Original%' "
    "AND title NOT LIKE '%(Tempt%' "
    "AND (synopsis NOT LIKE '%WOOW Original%' OR synopsis IS NULL) "
    "AND (synopsis NOT LIKE '%WOOW%' OR synopsis IS NULL) "
    "AND (synopsis NOT LIKE '%Tempt Original%' OR synopsis IS NULL)"
)

COMMON_SYNONYMS = {
    "phela": ["pehla", "phela"],
    "phel": ["pehl", "phel"],
    "pyaar": ["pyaar", "pyar"],
    "pyar": ["pyar", "pyaar"],
    "squidgame": ["squid game", "squid"],
    "spiderman": ["spider-man", "spider man"],
    "ironman": ["iron man", "iron-man"],
    "batman": ["bat-man", "bat man"],
    "punkjabi": ["punjabi"],
    "pujabi": ["punjabi"],
    "panjabi": ["punjabi"],
    "bolywood": ["bollywood"],
    "holywood": ["hollywood"],
}


def _build_search_clause(q_str: str) -> tuple[str, list]:
    q_str = (q_str or "").strip()
    if not q_str:
        return "1=1", []
    
    # 1. Exact phrase substring
    clauses = ["title LIKE ?"]
    params = [f"%{q_str}%"]
    
    # 2. Tokenized words with synonym/transliteration expansion
    words = [w for w in re.split(r'[\s\-]+', q_str.lower()) if len(w) >= 2]
    if words:
        word_clauses = []
        token_params = []
        for w in words:
            syns = COMMON_SYNONYMS.get(w, [w])
            sub_c = " OR ".join(["title LIKE ?" for _ in syns])
            word_clauses.append(f"({sub_c})")
            token_params.extend([f"%{s}%" for s in syns])
        
        token_combined = " AND ".join(word_clauses)
        clauses.append(f"({token_combined})")
        params.extend(token_params)
        
    return f"({' OR '.join(clauses)})", params




@app.get("/api/search")
def search_titles(q: str = "", limit: int = 10):
    """Instant search suggestions for search bar dropdown across 10,000+ movies."""
    q_str = (q or "").strip()
    if not q_str:
        return {"total": 0, "items": []}
    c = db()
    sq_clause, sq_params = _build_search_clause(q_str)
    sql_base = f"FROM movies WHERE {sq_clause} AND ({ADULT_EXCLUSION_SQL})"
    order_clause = (
        f"CASE "
        f"WHEN title LIKE ? THEN 0 "
        f"WHEN title LIKE ? THEN 1 "
        f"ELSE 2 END, "
        f"CAST(year AS INT) DESC, id DESC"
    )
    requested_limit = min(limit, 50)
    rank_params = sq_params + [f"{q_str}%", f"%{q_str}%", requested_limit + 1]
    rows = c.execute(
        f"SELECT id, title, year, poster, quality, imdb, is_series, source {sql_base} "
        f"ORDER BY {order_clause} LIMIT ?",
        rank_params
    ).fetchall()
    has_more = len(rows) > requested_limit
    items = [dict(r) for r in rows[:requested_limit]]
    return {"total": len(items), "has_more": has_more, "items": items}


@app.get("/api/genres")
def genres():
    return ["Bollywood", "Hollywood", "Punjabi", "South Special", "Action", "Comedy", "Drama", "Thriller", "Horror", "Romance", "Crime", "Mystery", "Sci-fi", "Animation"]


@app.get("/api/stats")
def stats():
    c = db()
    return {"movies": c.execute("SELECT COUNT(*) FROM movies WHERE is_series=0").fetchone()[0],
            "series": c.execute("SELECT COUNT(*) FROM movies WHERE is_series=1").fetchone()[0],
            "cached_streams": sum(1 for v in _resolver._memo.values() if v[1])}


@app.get("/api/health")
def health():
    """Fast liveness/readiness probe; it must never call a streaming provider."""
    try:
        from app.api.routes_catalog import get_db_connection
        with get_db_connection() as conn:
            conn.execute("SELECT 1 FROM movies LIMIT 1").fetchone()
    except Exception as exc:
        raise HTTPException(503, "catalogue database unavailable") from exc
    return {"ok": True, "catalogue": "ready", "time": int(time.time())}




# ------------------------------------------------------------------- HLS playlist rewriting / local-development proxy

_SEGMENT_SECRET = os.getenv("HLS_SEGMENT_SIGNING_SECRET", "").strip()
_SEGMENT_TTL_SECONDS = max(300, int(os.getenv("HLS_SEGMENT_TTL_SECONDS", "21600")))
_SEGMENT_ALLOWED_HOSTS = {
    host.strip().lower() for host in os.getenv("HLS_PROXY_ALLOWED_HOSTS", "").split(",") if host.strip()
}


def _segment_is_allowed(url: str) -> bool:
    """Do not turn the Nginx relay into a general-purpose internet proxy."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    return not _SEGMENT_ALLOWED_HOSTS or any(host == allowed or host.endswith(f".{allowed}") for allowed in _SEGMENT_ALLOWED_HOSTS)


def _evaluate_upstream_expiry(query_str: str, now: int) -> tuple[str, Optional[int], Optional[str]]:
    """Evaluate upstream token lifetime (s = start epoch, e = duration seconds).

    Distinguishes:
    1. Both 's' and 'e' absent -> ("absent", None, None)
    2. Both present and valid -> ("valid", s + e, None)
    3. Only one present -> ("partial", None, error_detail)
    4. Duplicated parameters -> ("duplicated", None, error_detail)
    5. Malformed or out-of-range -> ("malformed", None, error_detail)
    """
    if not query_str:
        return "absent", None, None

    try:
        qs = parse_qs(query_str, keep_blank_values=False)
    except Exception:
        return "malformed", None, "Unable to parse query parameters"

    has_s = "s" in qs
    has_e = "e" in qs

    if not has_s and not has_e:
        return "absent", None, None

    if has_s != has_e:
        missing_param = "e" if has_s else "s"
        return "partial", None, f"Partial upstream token: missing required parameter '{missing_param}'"

    s_list = qs["s"]
    e_list = qs["e"]

    if len(s_list) != 1 or len(e_list) != 1:
        return "duplicated", None, "Conflicting duplicated upstream token parameters"

    try:
        s_val = int(s_list[0])
        e_val = int(e_list[0])
    except (ValueError, TypeError):
        return "malformed", None, "Non-integer upstream token parameter values"

    # Validate against actual provider semantics:
    # 's' is a UNIX epoch start timestamp; 'e' is a positive duration in seconds
    if s_val < 1577836800 or s_val > now + 86400:
        return "malformed", None, f"Upstream start timestamp '{s_val}' is outside permitted range"
    if e_val <= 0 or e_val > 86400:
        return "malformed", None, f"Upstream duration '{e_val}' is outside permitted range"

    return "valid", s_val + e_val, None


def _signed_segment_url(url: str, now: Optional[int] = None) -> str:
    """Create an Nginx secure_link-compatible segment URL.
    
    Dynamically bounds expiration to the upstream authorization window (s + e)
    so local signatures never outlive upstream validity. Fails closed on any
    partial, duplicate, or malformed token parameters.
    """
    if not _SEGMENT_SECRET:
        return "/proxy/seg?u=" + quote(url, safe="")
    if not _segment_is_allowed(url):
        raise HTTPException(502, "HLS upstream host is not allow-listed")

    parsed = urlparse(url)
    target_host = parsed.netloc
    path_and_query = parsed.path.lstrip('/') + (f'?{parsed.query}' if parsed.query else '')
    raw_path = f'{target_host}/{path_and_query}'

    current_time = int(time.time()) if now is None else int(now)
    token_status, upstream_expiry, err_msg = _evaluate_upstream_expiry(parsed.query, current_time)

    if token_status == "valid":
        local_expiry = min(current_time + _SEGMENT_TTL_SECONDS, upstream_expiry)
        if local_expiry <= current_time:
            raise HTTPException(410, "Upstream stream authorization has expired")
    elif token_status == "absent":
        # Both absent: use fallback TTL only where appropriate for allowlisted hosts
        local_expiry = current_time + _SEGMENT_TTL_SECONDS
    else:
        # Fail closed on partial, duplicated, or malformed token parameters
        raise HTTPException(403, f"Upstream token error: {err_msg}")

    expires = str(local_expiry)
    digest = hashlib.md5(f'{expires}{raw_path} {_SEGMENT_SECRET}'.encode('utf-8'), usedforsecurity=False).digest()
    token = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')
    return f'/seg/{token}/{expires}/{raw_path}'


@app.api_route("/proxy/hls", methods=["GET", "HEAD"])
async def proxy_hls(u: str = Query(...)):
    """Fetch only playlists and route segment bytes to Nginx in production."""
    url = unquote(u)
    try:
        r = await _client.get(url, headers=headers_for(url), timeout=12)
    except Exception as e:
        raise HTTPException(504, f"upstream playlist error: {e}")
    if r.status_code >= 400:
        raise HTTPException(r.status_code, "upstream playlist error")
    base, text = str(r.url), r.text

    def absu(x): return urljoin(base, x)

    if "#EXT-X-STREAM-INF" in text or "#EXT-X-MEDIA:" in text:
        out = []
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                out.append("/proxy/hls?u=" + quote(absu(s), safe=""))
            elif s.startswith("#EXT-X-MEDIA:") and "URI=" in s:
                sub_fn = lambda m: f'URI="/proxy/hls?u={quote(absu(m.group(1)), safe="")}"'
                out.append(re.sub(r'URI="([^"]+)"', sub_fn, s))
            else:
                out.append(line)
    else:
        out = []
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(_signed_segment_url(absu(s)))
            elif s.startswith("#EXT-X-KEY") and "URI=" in s:
                sub_fn = lambda m: f'URI="{_signed_segment_url(absu(m.group(1)))}"'
                out.append(re.sub(r'URI="([^"]+)"', sub_fn, s))
            else:
                out.append(line)

    return Response("\n".join(out), media_type="application/vnd.apple.mpegurl",
                    headers={"Cache-Control": "no-cache"})


@app.api_route("/proxy/seg", methods=["GET", "HEAD"])
async def proxy_seg(u: str = Query(...), request: Request = None):
    """Local fallback only; production Nginx owns /seg byte relay."""
    if _SEGMENT_SECRET:
        raise HTTPException(404, "Production segment relay is served by Nginx")
    url = unquote(u)
    hdrs = headers_for(url)
    rng = request.headers.get("range") if request else None
    if rng:
        hdrs["Range"] = rng
    try:
        r = await _client.get(url, headers=hdrs, timeout=15)
    except Exception as e:
        raise HTTPException(504, f"upstream segment error: {e}")

    out = {"Content-Type": r.headers.get("content-type", "video/mp2t"),
           "Accept-Ranges": "bytes", "Cache-Control": "public, max-age=86400"}
    for k in ("content-range", "content-length"):
        if k in r.headers:
            out[k.title()] = r.headers[k]
    return Response(r.content, status_code=r.status_code, headers=out)


# ---------------------------------------------------------------- subtitles
_sub_cache: dict[int, str] = {}


@app.get("/api/subtitles/{mid}")
async def subtitles(mid: int):
    """Provide English WebVTT subtitles for each movie (Task 3)."""
    if mid in _sub_cache:
        return Response(_sub_cache[mid], media_type="text/vtt; charset=utf-8",
                        headers={"Access-Control-Allow-Origin": "*"})

    r = db().execute("SELECT title, year FROM movies WHERE id=?", (mid,)).fetchone()
    if not r:
        return Response("WEBVTT\n\n", media_type="text/vtt; charset=utf-8")

    title, year = r["title"] or "", r["year"] or ""
    clean_title = re.sub(r'\(\d{4}\).*', '', title).strip()
    query = f"{clean_title} {year}".strip()
    vtt = "WEBVTT\n\n"

    try:
        c_url = f"https://v3-cinemeta.strem.io/catalog/movie/top/search={quote(query)}.json"
        cr = await _client.get(c_url, timeout=5)
        metas = cr.json().get("metas", [])
        if metas:
            imdb_id = metas[0].get("id")
            s_url = f"https://opensubtitles-v3.strem.io/subtitles/movie/{imdb_id}.json"
            sr = await _client.get(s_url, timeout=5)
            subs = sr.json().get("subtitles", [])
            eng = [s for s in subs if s.get("lang") in ["eng", "en"]]
            if eng:
                sub_r = await _client.get(eng[0]["url"], timeout=6)
                srt_text = sub_r.text
                vtt = "WEBVTT\n\n" + re.sub(r'(\d\d:\d\d:\d\d),(\d\d\d)', r'\1.\2', srt_text)
    except Exception:
        pass

    _sub_cache[mid] = vtt
    return Response(vtt, media_type="text/vtt; charset=utf-8",
                    headers={"Access-Control-Allow-Origin": "*",
                             "Cache-Control": "public, max-age=86400"})


STATIC_DIR = Path(__file__).parent / "static"
WEB_DIR = Path(__file__).parent.parent / "web"

if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")

if STATIC_DIR.exists():
    # Explicit /assets mount for React production Vite assets (returns 404 for missing assets, not SPA index)
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # React SPA Fallback Routes for client-side deep linking
    @app.get("/movie/{full_path:path}")
    @app.get("/series/{full_path:path}")
    @app.get("/genre/{full_path:path}")
    @app.get("/my-list")
    @app.get("/search")
    @app.get("/profile")
    @app.get("/movies")
    async def serve_react_spa(full_path: str = ""):
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Frontend index not found")

    # Serve modern React frontend at root if present, otherwise fallback message
    @app.get("/")
    async def serve_root():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Cinemy API is running"}

    # Mount remaining root static files (favicon.svg, favicon.ico, etc.)
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
