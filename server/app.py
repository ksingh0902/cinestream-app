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

app = FastAPI(title="MyMovies API")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

_http = HttpClient(delay=0.0, cache_dir=None)
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


# ---------------------------------------------------------------- catalogue
@app.get("/api/movies")
def movies(q: Optional[str] = None, genre: Optional[str] = None,
           year: Optional[str] = None, series: Optional[int] = None,
           sort: str = "year", page: int = 1, per_page: int = 48):
    w, a = ["title IS NOT NULL AND title != ''"], []
    if q:      w.append("title LIKE ?");  a.append(f"%{q}%")
    if genre:  w.append("genres LIKE ?"); a.append(f'%"{genre}"%')
    if year:   w.append("year = ?");      a.append(year)
    if series is not None: w.append("is_series = ?"); a.append(series)
    order = {"year": "CAST(year AS INT) DESC", "recent": "updated_at DESC",
             "imdb": "CAST(imdb AS REAL) DESC", "title": "title"}.get(sort, "CAST(year AS INT) DESC")
    sql = "SELECT * FROM movies" + (" WHERE " + " AND ".join(w) if w else "")
    c = db()
    total = c.execute(sql.replace("SELECT *", "SELECT COUNT(*)"), a).fetchone()[0]
    rows = c.execute(sql + f" ORDER BY {order} LIMIT ? OFFSET ?",
                     a + [per_page, (page - 1) * per_page]).fetchall()
    return {"total": total, "page": page, "per_page": per_page,
            "items": [_row(r) for r in rows]}


@app.get("/api/movie/{mid}")
def movie(mid: int):
    r = db().execute("SELECT * FROM movies WHERE id=?", (mid,)).fetchone()
    if not r:
        raise HTTPException(404, "not found")
    return _row(r)


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


# ------------------------------------------------------- stream (self-heal)
def _embeds(row) -> list[dict]:
    return json.loads(row["embeds"] or "[]")


@app.get("/api/stream/{mid}")
def stream(mid: int, fresh: int = 0):
    """R1/R2/R3: cached -> live -> re-scrape page -> failover."""
    r = db().execute("SELECT * FROM movies WHERE id=?", (mid,)).fetchone()
    if not r:
        raise HTTPException(404, "not found")

    embeds = _embeds(r)

    # 1. warm cache
    if not fresh:
        for e in embeds:
            if (d := _resolver.cached(e["code"])):
                return _payload(mid, e, d)

    # 2. live resolve, trying every known embed
    for e in embeds:
        if (d := _resolver.resolve(e["code"], e.get("url"), force=True)):
            return _payload(mid, e, d)

    # 3. embeds stale -> re-scrape the movie page to rediscover current hosts
    try:
        html = _http.get(r["url"], force=True)
        info = parse_detail(html, r["url"])
        if info["embeds"]:
            from scraper.store import upsert
            con = db()
            info.update({k: r[k] for k in ("title", "year") if r[k]})
            upsert(con, info)
            for e in info["embeds"]:
                if (d := _resolver.resolve(e["code"], e["url"], force=True)):
                    return _payload(mid, e, d)
    except Exception:
        pass

    raise HTTPException(502, "no playable stream")


def _payload(mid: int, embed: dict, data: dict) -> dict:
    return {"movie_id": mid, "code": embed["code"], "host": embed.get("host"),
            "duration_s": data.get("duration_s"),
            "expires_in": STREAM_TTL,
            "play": "/proxy/hls?u=" + quote(data["hls"], safe="")}


# ------------------------------------------------------------------- proxy
@app.api_route("/proxy/hls", methods=["GET", "HEAD"])
async def proxy_hls(u: str = Query(...)):
    """Rewrite master + media playlists so hls.js is never CORS-blocked (R4)."""
    url = unquote(u)
    r = await _client.get(url, headers=headers_for(url))
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
    r = await _client.get(url, headers=hdrs)

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


app.mount("/", StaticFiles(directory=str(Path(__file__).parent / "static"),
                           html=True), name="static")
