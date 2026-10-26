"""Backend: catalogue + self-healing stream resolver + CORS-proof HLS proxy."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote, urljoin

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from config import DB_PATH, STREAM_TTL, UA
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
    global _sync_task
    if os.getenv("DISABLE_AUTO_SYNC", "0") != "1":
        _sync_task = asyncio.create_task(_periodic_sync_loop())

@app.on_event("shutdown")
async def shutdown_sync_scheduler():
    global _sync_task
    if _sync_task:
        _sync_task.cancel()

@app.post("/api/sync/latest")
async def trigger_sync():
    """Manual or cron trigger to immediately sync latest movies from Yomovies & Ask4movie."""
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
    "AND title NOT LIKE '%Jugnutv%'"
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
    total = c.execute(f"SELECT COUNT(*) {sql_base}", sq_params).fetchone()[0]
    
    order_clause = (
        f"CASE "
        f"WHEN title LIKE ? THEN 0 "
        f"WHEN title LIKE ? THEN 1 "
        f"ELSE 2 END, "
        f"CAST(year AS INT) DESC, id DESC"
    )
    rank_params = sq_params + [f"{q_str}%", f"%{q_str}%", min(limit, 50)]
    rows = c.execute(
        f"SELECT id, title, year, poster, quality, imdb, is_series {sql_base} "
        f"ORDER BY {order_clause} LIMIT ?",
        rank_params
    ).fetchall()
    return {"total": total, "items": [dict(r) for r in rows]}


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
    """R9: is upstream alive, how many streams are warm."""
    try:
        _http.get("https://yomovies.wine/", force=True)
        site = "ok"
    except Exception as e:
        site = f"fail: {e}"
    return {"site": site, "cached_streams": stats()["cached_streams"],
            "ttl_seconds": STREAM_TTL, "time": int(time.time())}




# ------------------------------------------------------------------- proxy
@app.api_route("/proxy/hls", methods=["GET", "HEAD"])
async def proxy_hls(u: str = Query(...)):
    """Rewrite master + media playlists so hls.js is never CORS-blocked (R4)."""
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
                out.append("/proxy/seg?u=" + quote(absu(s), safe=""))
            elif s.startswith("#EXT-X-KEY") and "URI=" in s:
                sub_fn = lambda m: f'URI="/proxy/seg?u={quote(absu(m.group(1)), safe="")}"'
                out.append(re.sub(r'URI="([^"]+)"', sub_fn, s))
            else:
                out.append(line)

    return Response("\n".join(out), media_type="application/vnd.apple.mpegurl",
                    headers={"Cache-Control": "no-cache"})


@app.api_route("/proxy/seg", methods=["GET", "HEAD"])
async def proxy_seg(u: str = Query(...), request: Request = None):
    """Stream segment/key bytes, forwarding Range so seeking works (R4)."""
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


app.mount("/web", StaticFiles(directory=str(Path(__file__).parent.parent / "web")),
          name="web")
app.mount("/", StaticFiles(directory=str(Path(__file__).parent / "static"),
                           html=True), name="static")
