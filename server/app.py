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

app = FastAPI(title="CineMyMovies API")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

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
    "quality != '18+' AND (quality NOT LIKE '%18+%' OR quality IS NULL) "
    "AND (genres NOT LIKE '%\"Erotic Movies\"%' OR genres IS NULL) "
    "AND title NOT LIKE '%(Ullu%' "
    "AND title NOT LIKE '%(PrimeShots%' "
    "AND title NOT LIKE '%(Hunters%' "
    "AND title NOT LIKE '%(WOOW%' "
    "AND title NOT LIKE '%(HuntCinema%' "
    "AND title NOT LIKE '%(Mastiplay%' "
    "AND title NOT LIKE '%(BulbulPlay%' "
    "AND title NOT LIKE '%(Besharams%' "
    "AND title NOT LIKE '%(Kaddu%' "
    "AND title NOT LIKE '%(DesiPrime%' "
    "AND title NOT LIKE '%(Hotshots%' "
    "AND title NOT LIKE '%(MoodX%' "
    "AND title NOT LIKE '%(Voovi%' "
    "AND title NOT LIKE '%(Chikooflix%' "
    "AND title NOT LIKE '%(Bigshots%' "
    "AND title NOT LIKE '%(Atrangii%' "
    "AND title NOT LIKE '%(Altbalaji%' "
    "AND title NOT LIKE '%(Jugnutv%' "
    "AND title NOT LIKE '%(Rabbit%'"
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


# ---------------------------------------------------------------- catalogue
@app.get("/api/movies")
def movies(q: Optional[str] = None, genre: Optional[str] = None,
           year: Optional[str] = None, series: Optional[int] = None,
           sort: str = "recent", page: int = 1, per_page: int = 48):
    w, a = ["title IS NOT NULL AND title != ''", ADULT_EXCLUSION_SQL], []
    q_str = (q or "").strip()
    if q_str:
        sq_clause, sq_params = _build_search_clause(q_str)
        w.append(sq_clause)
        a.extend(sq_params)
    if genre:
        w.append("(genres LIKE ? OR quality = ? OR title LIKE ?)")
        a.extend([f'%"{genre}"%', genre, f"%{genre}%"])
    if year:   w.append("year = ?");      a.append(year)
    if series is not None: w.append("is_series = ?"); a.append(series)

    if q_str:
        # Prioritize exact prefix, exact substring, then date
        order = f"CASE WHEN title LIKE ? THEN 0 WHEN title LIKE ? THEN 1 ELSE 2 END, CAST(year AS INT) DESC, id ASC"
        order_params = [f"{q_str}%", f"%{q_str}%"]
    else:
        order_map = {
            "recent": "CAST(year AS INT) DESC, id ASC",
            "year": "CAST(year AS INT) DESC, id ASC",
            "imdb": "CAST(REPLACE(REPLACE(imdb, 'IMDb: ', ''), '★ ', '') AS REAL) DESC, CAST(year AS INT) DESC, id ASC",
            "title": "title ASC, CAST(year AS INT) DESC"
        }
        order = order_map.get(sort, "CAST(year AS INT) DESC, id ASC")
        order_params = []

    sql = "SELECT * FROM movies" + (" WHERE " + " AND ".join(w) if w else "")
    c = db()
    total = c.execute(sql.replace("SELECT *", "SELECT COUNT(*)"), a).fetchone()[0]
    rows = c.execute(sql + f" ORDER BY {order} LIMIT ? OFFSET ?",
                     a + order_params + [per_page, (page - 1) * per_page]).fetchall()
    return {"total": total, "page": page, "per_page": per_page,
            "items": [_row(r) for r in rows]}


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
        f"CAST(year AS INT) DESC, id ASC"
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


def _is_speedo(e: dict) -> bool:
    host = (e.get("host") or "").lower()
    url = (e.get("url") or "").lower()
    return e.get("type") == "speedo" or "speedo" in host or "/embed-" in url


def _embed_payload(mid: int, embed: dict) -> dict:
    return {
        "movie_id": mid,
        "code": embed.get("code", "embed"),
        "host": embed.get("host", "vidsrc"),
        "type": "embed",
        "duration_s": None,
        "expires_in": STREAM_TTL,
        "play": embed["url"]
    }


def _payload(mid: int, embed: dict, data: dict) -> dict:
    return {
        "movie_id": mid,
        "code": embed["code"],
        "host": embed.get("host"),
        "type": "hls",
        "duration_s": data.get("duration_s"),
        "expires_in": STREAM_TTL,
        "play": "/proxy/hls?u=" + quote(data["hls"], safe="")
    }


@app.get("/api/stream/{mid}")
async def stream(mid: int, fresh: int = 0):
    """R1/R2/R3/R4: cached -> live -> re-scrape page -> fallback embed."""
    r = db().execute("SELECT * FROM movies WHERE id=?", (mid,)).fetchone()
    if not r:
        raise HTTPException(404, "not found")

    embeds = _embeds(r)

    # If no embeds in DB, scrape the movie page immediately
    if not embeds:
        try:
            html = _http.get(r["url"], force=True)
            info = parse_detail(html, r["url"])
            if info["embeds"]:
                embeds = info["embeds"]
                con = db()
                con.execute("UPDATE movies SET embeds=? WHERE id=?", (json.dumps(embeds), mid))
                con.commit()
        except Exception:
            pass

    # 1. Try Speedostream HLS cache & resolve
    speedo_list = [e for e in embeds if _is_speedo(e)]
    if not fresh:
        for e in speedo_list:
            if (d := _resolver.cached(e["code"])):
                return _payload(mid, e, d)

    for e in speedo_list:
        if (d := _resolver.resolve(e["code"], e.get("url"), force=True)):
            return _payload(mid, e, d)

    # 2. Try iframe / vidsrc embeds
    iframe_list = [e for e in embeds if not _is_speedo(e)]
    for e in iframe_list:
        if e.get("url"):
            return _embed_payload(mid, e)

    # 3. If still empty, re-scrape the movie page
    try:
        html = _http.get(r["url"], force=True)
        info = parse_detail(html, r["url"])
        if info["embeds"]:
            con = db()
            con.execute("UPDATE movies SET embeds=? WHERE id=?", (json.dumps(info["embeds"]), mid))
            con.commit()
            for e in info["embeds"]:
                if _is_speedo(e):
                    if (d := _resolver.resolve(e["code"], e.get("url"), force=True)):
                        return _payload(mid, e, d)
                elif e.get("url"):
                    return _embed_payload(mid, e)
    except Exception:
        pass

    # 4. Fallback: Lookup IMDb ID from Cinemeta ONLY for Hollywood/International titles
    # Vidsrc does not host regional Indian/Punjabi cinema (causes "MEDIA NOT FOUND")
    genres = (r["genres"] or "").lower()
    title_lower = (r["title"] or "").lower()
    is_regional = any(k in genres for k in ["punjabi", "bollywood", "marathi", "bengali", "tamil", "telugu"]) or \
                  any(k in title_lower for k in ["punjabi", "hindi", "bengali", "marathi", "tamil", "telugu", "season"])
    if not is_regional:
        try:
            clean_title = re.sub(r'\(\d{4}\).*', '', r["title"] or "").strip()
            query = f"{clean_title} {r['year'] or ''}".strip()
            c_url = f"https://v3-cinemeta.strem.io/catalog/movie/top/search={quote(query)}.json"
            cr = await _client.get(c_url, timeout=4)
            metas = cr.json().get("metas", [])
            if metas and metas[0].get("id") and str(metas[0]["id"]).startswith("tt"):
                meta_name = (metas[0].get("name") or "").lower()
                clean_name = re.sub(r'[^a-z0-9 ]', '', clean_title.lower()).strip()
                if clean_name and (clean_name in meta_name or meta_name in clean_name):
                    imdb_id = metas[0]["id"]
                    fallback_embed = {
                        "code": imdb_id,
                        "host": "vidsrc.sh",
                        "url": f"https://vidsrc.sh/embed/movie?imdb={imdb_id}",
                        "type": "embed"
                    }
                    return _embed_payload(mid, fallback_embed)
        except Exception:
            pass

    raise HTTPException(502, "no playable stream")


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


app.mount("/", StaticFiles(directory=str(Path(__file__).parent / "static"),
                           html=True), name="static")
