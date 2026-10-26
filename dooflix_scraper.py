"""Probe and import an authorized DooFlix-compatible JSON catalogue.

The upstream URL and captured request headers are intentionally configuration,
not constants: no usable request URL or response sample was supplied with this
project.  The scraper emits portable files and can upsert directly into the
existing CineMyMovies ``movies`` table.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import logging
import re
import sqlite3
import statistics
import time
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlparse, urlunparse

import requests

LOG = logging.getLogger("dooflix")
SOURCE = "dooflix"

TITLE_KEYS = ("title", "name", "movie_name", "original_title")
POSTER_KEYS = ("poster", "poster_url", "image", "image_url", "thumbnail", "cover", "backdrop")
ID_KEYS = ("id", "movie_id", "content_id", "video_id", "tmdb_id", "imdb_id", "slug")
YEAR_KEYS = ("year", "release_year", "released", "release_date", "date")
RUNTIME_KEYS = ("runtime", "runtime_min", "duration", "duration_min", "length")
GENRE_KEYS = ("genres", "genre", "categories", "category")
DIRECTOR_KEYS = ("director", "directors")
WRITER_KEYS = ("writer", "writers", "screenplay")
CAST_KEYS = ("cast", "stars", "actors", "starring")
RATING_KEYS = ("rating", "imdb", "imdb_rating", "score", "vote_average")
QUALITY_KEYS = ("quality", "video_quality", "resolution")
COUNTRY_KEYS = ("country", "countries", "origin_country")
SYNOPSIS_KEYS = ("synopsis", "overview", "description", "plot", "summary", "story")
TYPE_KEYS = ("type", "content_type", "media_type", "kind")

PROBE_PATHS = (
    "/api/movies", "/api/movie", "/api/v1/movies", "/api/v1/movie",
    "/api/v2/movies", "/v1/movies", "/v2/movies", "/movies", "/movie",
    "/api/catalog", "/api/v1/catalog", "/catalog", "/api/home", "/api/v1/home",
    "/home", "/api/latest", "/api/v1/latest", "/latest", "/api/content",
    "/api/v1/content", "/content", "/api/videos", "/api/v1/videos", "/videos",
    "/api/discover", "/api/v1/discover",
)

URL_RE = re.compile(r"(?:(?:https?:)?//[^\s\"'<>\\]+|/[^\s\"'<>\\]+)", re.I)
MEDIA_EXT_RE = re.compile(r"\.(?:m3u8|mpd|mp4)(?:[?#][^\s\"'<>\\]*)?$", re.I)
EMBED_RE = re.compile(r"/(?:embed|player|watch|e)(?:/|\?|$)", re.I)
SERIES_RE = re.compile(r"\b(?:series|tv|show|episode|season)\b", re.I)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2}|21\d{2})\b")


@dataclass
class Movie:
    """Normalized DooFlix movie record."""

    source_id: str
    title: str
    slug: str
    year: int | None
    runtime_min: int | None
    genres: list[str] = field(default_factory=list)
    director: list[str] = field(default_factory=list)
    writers: list[str] = field(default_factory=list)
    cast: list[str] = field(default_factory=list)
    rating: float | None = None
    quality: str = ""
    country: list[str] = field(default_factory=list)
    date: str = ""
    synopsis: str = ""
    poster: str = ""
    streams: list[str] = field(default_factory=list)
    embeds: list[str] = field(default_factory=list)
    is_series: bool = False
    is_hindi_dubbed: bool = False
    source: str = SOURCE
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def parse_pairs(values: Sequence[str], separator: str) -> dict[str, str]:
    """Parse repeatable KEY<separator>VALUE command-line options."""
    parsed: dict[str, str] = {}
    for raw in values:
        if separator not in raw:
            raise ValueError(f"Expected {separator!r} in {raw!r}")
        key, value = raw.split(separator, 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Empty key in {raw!r}")
        parsed[key] = value.strip()
    return parsed


def slugify(title: str, year: int | None) -> str:
    """Return the site's lowercase ``title-year`` slug."""
    raw = f"{title}-{year}" if year else title
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return slug or "untitled"


def runtime_minutes(value: Any) -> int | None:
    """Normalize numeric, minute, hour/minute and HH:MM runtime values."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None
    text = str(value).strip().lower()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    clock = re.fullmatch(r"(\d{1,2}):(\d{1,2})(?::\d{1,2})?", text)
    if clock:
        return int(clock.group(1)) * 60 + int(clock.group(2))
    hours = re.search(r"(\d+)\s*(?:h|hr|hour)s?", text)
    minutes = re.search(r"(\d+)\s*(?:m|min|minute)s?", text)
    if hours or minutes:
        return (int(hours.group(1)) * 60 if hours else 0) + (int(minutes.group(1)) if minutes else 0)
    number = re.search(r"\d+", text)
    return int(number.group()) if number else None


def walk_lists(value: Any) -> Iterator[list[dict[str, Any]]]:
    """Yield every recursively discovered non-empty list of mappings."""
    if isinstance(value, list):
        mappings = [item for item in value if isinstance(item, dict)]
        if mappings:
            yield mappings
        for item in value:
            yield from walk_lists(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from walk_lists(item)


def normalized_mapping(record: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key).strip().lower(): value for key, value in record.items()}


def first(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, "", [], {}):
            return record[key]
    return None


def text_list(value: Any) -> list[str]:
    """Convert strings, scalar values or lists of objects into clean labels."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"\s*(?:\||,|/|;)\s*", value.strip())
        return [part for part in parts if part]
    if isinstance(value, Mapping):
        label = first(normalized_mapping(value), ("name", "title", "label", "value"))
        return [str(label).strip()] if label else []
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        out: list[str] = []
        for item in value:
            out.extend(text_list(item))
        return unique(out)
    return [str(value).strip()]


def unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        clean = value.strip()
        marker = clean.casefold()
        if clean and marker not in seen:
            seen.add(marker)
            out.append(clean)
    return out


def absolute_url(raw: str, base_url: str) -> str:
    candidate = html.unescape(unquote(raw)).replace("\\/", "/").strip(" \"'(),[]{}")
    if candidate.startswith("//"):
        return f"{urlparse(base_url).scheme or 'https'}:{candidate}"
    return urljoin(base_url, candidate)


def extract_media(value: Any, base_url: str) -> tuple[list[str], list[str]]:
    """Scan serialized and URL-decoded payload text for stream and embed URLs."""
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    scans = (raw, unquote(raw), raw.replace("\\/", "/"), unquote(raw).replace("\\/", "/"))
    streams: list[str] = []
    embeds: list[str] = []
    for scan in scans:
        for match in URL_RE.findall(scan):
            url = absolute_url(match, base_url)
            path = urlparse(url).path
            if MEDIA_EXT_RE.search(path + (f"?{urlparse(url).query}" if urlparse(url).query else "")):
                streams.append(url)
            elif EMBED_RE.search(path):
                embeds.append(url)
    return unique(streams), unique(embeds)


def movie_like(record: Mapping[str, Any]) -> bool:
    normalized = normalized_mapping(record)
    return bool(first(normalized, TITLE_KEYS) and (first(normalized, POSTER_KEYS) or first(normalized, ID_KEYS)))


def parse_year(value: Any) -> int | None:
    match = YEAR_RE.search(str(value or ""))
    return int(match.group(1)) if match else None


def parse_rating(value: Any) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return float(match.group()) if match else None


def is_series(record: Mapping[str, Any]) -> bool:
    normalized = normalized_mapping(record)
    candidates = [first(normalized, TYPE_KEYS), normalized.get("is_series"), normalized.get("series")]
    return any(value is True or SERIES_RE.search(str(value or "")) for value in candidates)


def normalize_movie(record: Mapping[str, Any], base_url: str) -> Movie | None:
    """Normalize one shape-agnostic movie candidate."""
    data = normalized_mapping(record)
    title = str(first(data, TITLE_KEYS) or "").strip()
    if not title:
        return None
    year = parse_year(first(data, YEAR_KEYS))
    raw_id = first(data, ID_KEYS)
    if raw_id in (None, ""):
        raw_id = hashlib.sha256(f"{title}|{year or ''}".encode()).hexdigest()[:20]
    poster_value = first(data, POSTER_KEYS)
    poster = absolute_url(str(poster_value), base_url) if poster_value else ""
    streams, embeds = extract_media(record, base_url)
    is_ser = is_series(record)
    # Never turn a catalogue/post ID into a player URL. DooFlix's playback
    # resolver uses TMDB IDs, while these raw IDs belong only to the catalogue.
    # A record without media remains unresolved until the server can map its
    # title to TMDB and ask the live DooFlix resolver.
    return Movie(
        source_id=str(raw_id), title=title, slug=slugify(title, year), year=year,
        runtime_min=runtime_minutes(first(data, RUNTIME_KEYS)),
        genres=text_list(first(data, GENRE_KEYS)), director=text_list(first(data, DIRECTOR_KEYS)),
        writers=text_list(first(data, WRITER_KEYS)), cast=text_list(first(data, CAST_KEYS)),
        rating=parse_rating(first(data, RATING_KEYS)), quality=str(first(data, QUALITY_KEYS) or "").strip(),
        country=text_list(first(data, COUNTRY_KEYS)), date=str(first(data, ("date", "release_date", "released")) or "").strip(),
        synopsis=str(first(data, SYNOPSIS_KEYS) or "").strip(), poster=poster,
        streams=streams, embeds=embeds, is_series=is_ser,
    )


class Client:
    """One-session HTTP client with delay and exponential retry."""

    def __init__(self, headers: Mapping[str, str], delay: float, timeout: float, retries: int) -> None:
        self.session = requests.Session()
        self.session.headers.update(headers)
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self._last_request = 0.0

    def close(self) -> None:
        self.session.close()

    def get(self, url: str, *, params: Mapping[str, Any] | None = None) -> requests.Response:
        """GET with polite pacing and retry for throttling/transient server errors."""
        for attempt in range(self.retries + 1):
            wait = self.delay - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            response = self.session.get(url, params=params, timeout=self.timeout)
            self._last_request = time.monotonic()
            if response.status_code != 429 and response.status_code < 500:
                response.raise_for_status()
                return response
            if attempt >= self.retries:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After", "")
            backoff = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 2 ** attempt
            time.sleep(min(backoff, 30.0))
        raise RuntimeError("unreachable")


def page_url(endpoint: str, page: int) -> str:
    url = endpoint
    if "{page}" in url:
        url = url.replace("{page}", str(page))
    if "{skip}" in url:
        url = url.replace("{skip}", str((page - 1) * 50))
    return url


def collect_movies(payload: Any, base_url: str, *, movies_only: bool, min_runtime: int,
                   since: str | None) -> list[Movie]:
    """Find and normalize all movie-like mappings in a JSON payload."""
    records: list[Mapping[str, Any]] = []
    for group in walk_lists(payload):
        records.extend(record for record in group if movie_like(record))
    if isinstance(payload, dict) and movie_like(payload):
        records.append(payload)

    out: list[Movie] = []
    seen: set[str] = set()
    for record in records:
        try:
            if movies_only and is_series(record):
                continue
            movie = normalize_movie(record, base_url)
            if not movie or movie.source_id in seen:
                continue
            if movie.runtime_min is not None and movie.runtime_min < min_runtime:
                continue
            if since and movie.date and movie.date[:10] < since:
                continue
            seen.add(movie.source_id)
            out.append(movie)
        except Exception as exc:  # noqa: BLE001 - one malformed item must not abort a run
            LOG.warning("Skipping malformed record: %s", exc)
    return out


def load_cache(path: Path) -> dict[str, list[str]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def resolve_embeds(client: Client, movies: list[Movie], cache_path: Path) -> None:
    """Resolve stream URLs exposed by authorized embed pages and cache results."""
    cache = load_cache(cache_path)
    for movie in movies:
        for embed in movie.embeds:
            if embed in cache:
                movie.streams = unique([*movie.streams, *cache[embed]])
                continue
            try:
                response = client.get(embed)
                streams, _ = extract_media(response.text, response.url)
                cache[embed] = streams
                movie.streams = unique([*movie.streams, *streams])
            except Exception as exc:  # noqa: BLE001
                LOG.warning("Could not resolve embed for %s: %s", movie.title, exc)
    cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def content_html(movie: Movie) -> str:
    """Render the requested WordPress body field order and player markup."""
    values = (
        ("Title", movie.title), ("Genres", ", ".join(movie.genres)),
        ("Director", ", ".join(movie.director)), ("Writers", ", ".join(movie.writers)),
        ("Stars", ", ".join(movie.cast)),
        ("Duration", f"{movie.runtime_min} min" if movie.runtime_min else ""),
        ("Date", movie.date), ("Rating", movie.rating if movie.rating is not None else ""),
        ("Quality", movie.quality), ("Country", ", ".join(movie.country)),
    )
    details = "<p>" + "<br>\n".join(
        f"<strong>{label}:</strong> {html.escape(str(value))}" for label, value in values
    ) + "</p>"
    heading = f"<h2>How To Stream Free {html.escape(movie.title)} Movie On Cinemymovies?</h2>"
    synopsis = "".join(f"<p>{html.escape(part.strip())}</p>" for part in re.split(r"\n\s*\n", movie.synopsis) if part.strip())
    player = movie.streams[0] if movie.streams else (movie.embeds[0] if movie.embeds else "")
    iframe = (f'<iframe src="{html.escape(player, quote=True)}" width="100%" height="430" '
              'frameborder="0" scrolling="no" allowfullscreen referrerpolicy="origin"></iframe>') if player else ""
    return "\n".join(part for part in (details, heading, synopsis, iframe) if part)


def wordpress_record(movie: Movie) -> dict[str, Any]:
    primary = movie.genres[0] if movie.genres else "Movie"
    categories = ([f"{movie.year} Movies"] if movie.year else []) + [f"{genre} Movies" for genre in movie.genres]
    now = datetime.now(timezone.utc)
    poster_name = f"{movie.title}-{movie.year or 'unknown'}-movie.webp"
    poster_path = f"/wp-content/uploads/{now:%Y/%m}/{poster_name}"
    return {
        "title": movie.title, "slug": movie.slug, "status": "publish",
        "content": content_html(movie), "categories": unique(categories),
        "tags": [f"Watch {movie.year or ''} {primary} Movies".replace("  ", " ")],
        "meta": {
            "poster": movie.poster, "poster_target": poster_path, "year": movie.year,
            "runtime": movie.runtime_min, "rating": movie.rating, "quality": movie.quality,
            "country": " | ".join(movie.country),
            "stream": movie.streams[0] if movie.streams else "",
            "embed": movie.embeds[0] if movie.embeds else "", "source_id": movie.source_id,
        },
    }


def write_outputs(out_dir: Path, movies: list[Movie], elapsed: float) -> None:
    """Write JSONL, CSV, streams, WordPress import and summary files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    records = [asdict(movie) for movie in movies]
    with (out_dir / "movies.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    fields = list(Movie.__dataclass_fields__)
    with (out_dir / "movies.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({key: "|".join(value) if isinstance(value, list) else value for key, value in record.items()})
    streams = {movie.source_id: {"title": movie.title, "streams": movie.streams, "embeds": movie.embeds} for movie in movies}
    (out_dir / "streams.json").write_text(json.dumps(streams, indent=2, ensure_ascii=False), encoding="utf-8")
    imports = [wordpress_record(movie) for movie in movies]
    (out_dir / "cinemymovies_import.json").write_text(json.dumps(imports, indent=2, ensure_ascii=False), encoding="utf-8")
    runtimes = [int(movie.runtime_min) for movie in movies if movie.runtime_min is not None and str(movie.runtime_min).isdigit()]
    years = [int(movie.year) for movie in movies if movie.year is not None and str(movie.year).isdigit()]
    summary = {
        "count": len(movies), "playable": sum(bool(movie.streams or movie.embeds) for movie in movies),
        "runtime_seconds": round(elapsed, 3),
        "runtime_min": {"min": min(runtimes) if runtimes else None, "max": max(runtimes) if runtimes else None,
                        "median": statistics.median(runtimes) if runtimes else None},
        "year_range": [min(years), max(years)] if years else [],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def ensure_movies_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL,
        slug TEXT, title TEXT NOT NULL, year INTEGER, poster_url TEXT,
        duration_s INTEGER, rating REAL, genres TEXT, synopsis TEXT,
        is_series INTEGER DEFAULT 0, detail_url TEXT, player_url TEXT,
        player_kind TEXT DEFAULT 'iframe', servers_json TEXT,
        resolved_at INTEGER, updated_at INTEGER, poster TEXT, url TEXT,
        quality TEXT, country TEXT, actors TEXT, director TEXT,
        UNIQUE(source, source_id))""")


def upsert_database(path: Path, movies: Sequence[Movie]) -> None:
    """Upsert into the existing CineMyMovies SQLite table."""
    from app.db.migrate import migrate_database
    migrate_database(str(path))
    with closing(sqlite3.connect(path, timeout=30)) as conn:
        ensure_movies_schema(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(movies)")}
        existing_slugs = {
            row[0]: (row[1], str(row[2]))
            for row in conn.execute("SELECT slug, source, source_id FROM movies WHERE slug IS NOT NULL")
        }
        for movie in movies:
            stream = movie.streams[0] if movie.streams else (movie.embeds[0] if movie.embeds else None)
            is_hls = bool(movie.streams and ".m3u8" in movie.streams[0].lower().split("#", 1)[0])
            player_url = f"/proxy/hls?u={quote(movie.streams[0], safe='')}" if is_hls else stream
            resolution_target = movie.embeds[0] if movie.embeds else stream
            server_urls = [
                f"/proxy/hls?u={quote(url, safe='')}"
                if ".m3u8" in url.lower().split("#", 1)[0] else url
                for url in [*movie.streams, *movie.embeds]
            ]
            unique_url = f"https://dooflix.app/watch/{movie.source_id}"

            slug_cand = movie.slug or f"doo-{movie.source_id}"
            if not slug_cand.startswith("doo-"):
                slug_cand = f"doo-{slug_cand}"
            owner = existing_slugs.get(slug_cand)
            if owner and owner != (SOURCE, str(movie.source_id)):
                clean_sid = re.sub(r"[^a-z0-9]+", "-", str(movie.source_id).lower()).strip("-")
                slug_cand = f"{slug_cand}-{clean_sid}"
                c = 1
                while slug_cand in existing_slugs and existing_slugs[slug_cand] != (SOURCE, str(movie.source_id)):
                    c += 1
                    slug_cand = f"{slug_cand}-{c}"
            existing_slugs[slug_cand] = (SOURCE, str(movie.source_id))

            values: dict[str, Any] = {
                "source": SOURCE, "source_id": str(movie.source_id), "slug": slug_cand,
                "title": movie.title, "year": movie.year, "poster_url": movie.poster,
                "poster": movie.poster, "duration_s": movie.runtime_min * 60 if movie.runtime_min else None,
                "rating": movie.rating, "genres": json.dumps(movie.genres), "synopsis": movie.synopsis,
                # Prefer direct playback while retaining an embed as the durable
                # re-resolution target when the media URL is signed/short-lived.
                "is_series": 1 if movie.is_series else 0, "detail_url": resolution_target or unique_url,
                "url": unique_url, "player_url": player_url,
                "player_kind": "hls" if is_hls else "iframe",
                "servers_json": json.dumps([{"label": "DooFlix", "url": url} for url in server_urls]),
                "resolved_at": int(time.time()) if stream else None, "updated_at": int(time.time()),
                "quality": movie.quality, "country": json.dumps(movie.country),
                "actors": json.dumps(movie.cast), "director": json.dumps(movie.director),
                "is_hindi_dubbed": 1 if (getattr(movie, "is_hindi_dubbed", False) or any("dub" in g.lower() for g in movie.genres)) else 0,
            }
            values = {key: value for key, value in values.items() if key in columns}
            names = ",".join(values)
            placeholders = ",".join(f":{key}" for key in values)
            updates = ",".join(f"{key}=excluded.{key}" for key in values if key not in {"source", "source_id"})
            conn.execute(f"INSERT INTO movies ({names}) VALUES ({placeholders}) "
                         f"ON CONFLICT(source,source_id) DO UPDATE SET {updates}", values)
        conn.commit()
    if path.name == "cinemymovies.sqlite3" and Path("yomovies.db").exists():
        upsert_database(Path("yomovies.db"), movies)


def scrape(args: argparse.Namespace) -> int:
    headers = parse_pairs(args.header, ":")
    queries = parse_pairs(args.query, "=")
    client = Client(headers, args.delay, args.timeout, args.retries)
    started = time.monotonic()
    movies: list[Movie] = []
    seen_ids: set[str] = set()
    try:
        for page in range(args.start_page, args.start_page + args.max_pages):
            params = dict(queries)
            if "{page}" not in args.url and args.page_param:
                params[args.page_param] = str(page)
            response = client.get(page_url(args.url, page), params=params)
            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError(f"Expected JSON from {response.url}") from exc
            page_movies = collect_movies(payload, response.url, movies_only=args.movies_only,
                                          min_runtime=args.min_runtime, since=args.since)
            new_movies = [movie for movie in page_movies if movie.source_id not in seen_ids]
            LOG.info("page=%s candidates=%s new=%s", page, len(page_movies), len(new_movies))
            if not page_movies or not new_movies:
                break
            for movie in new_movies:
                seen_ids.add(movie.source_id)
                movies.append(movie)
                if args.limit and len(movies) >= args.limit:
                    break
            if args.limit and len(movies) >= args.limit:
                break
        if args.resolve_streams:
            resolve_embeds(client, movies, Path(args.out) / "stream_cache.json")
    finally:
        client.close()
    write_outputs(Path(args.out), movies, time.monotonic() - started)
    if args.db:
        upsert_database(Path(args.db), movies)
    LOG.info("wrote %d movies to %s", len(movies), args.out)
    return 0


def probe(args: argparse.Namespace) -> int:
    headers = parse_pairs(args.header, ":")
    queries = parse_pairs(args.query, "=")
    client = Client(headers, args.delay, args.timeout, args.retries)
    found = 0
    try:
        for path in PROBE_PATHS:
            url = urljoin(args.base.rstrip("/") + "/", path.lstrip("/"))
            try:
                response = client.get(url, params=queries)
                payload = response.json()
                candidates = collect_movies(payload, response.url, movies_only=False, min_runtime=0, since=None)
                if candidates:
                    found += 1
                    print(f"MATCH {response.status_code} {url} movies={len(candidates)}")
                else:
                    print(f"JSON  {response.status_code} {url} movies=0")
            except Exception as exc:  # noqa: BLE001
                print(f"MISS  {url} {type(exc).__name__}")
    finally:
        client.close()
    return 0 if found else 2


def parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--verbose", action="store_true")
    subs = root.add_subparsers(dest="command", required=True)

    def common(target: argparse.ArgumentParser) -> None:
        target.add_argument("--header", action="append", default=[], metavar="K: V")
        target.add_argument("--query", action="append", default=[], metavar="k=v")
        target.add_argument("--delay", type=float, default=0.8)
        target.add_argument("--timeout", type=float, default=20.0)
        target.add_argument("--retries", type=int, default=4)

    probe_parser = subs.add_parser("probe", help="test likely JSON catalogue paths")
    probe_parser.add_argument("--base", required=True)
    common(probe_parser)
    probe_parser.set_defaults(func=probe)

    scrape_parser = subs.add_parser("scrape", help="scrape a captured catalogue endpoint")
    scrape_parser.add_argument("--url", required=True, help="captured endpoint; may contain {page}")
    common(scrape_parser)
    scrape_parser.add_argument("--page-param", default="page")
    scrape_parser.add_argument("--start-page", type=int, default=1)
    scrape_parser.add_argument("--max-pages", type=int, default=1000)
    scrape_parser.add_argument("--movies-only", action=argparse.BooleanOptionalAction, default=True)
    scrape_parser.add_argument("--min-runtime", type=int, default=40)
    scrape_parser.add_argument("--since", help="minimum YYYY-MM-DD when a date is present")
    scrape_parser.add_argument("--limit", type=int, default=0)
    scrape_parser.add_argument("--resolve-streams", action="store_true")
    scrape_parser.add_argument("--out", default="./cinemymovies_data")
    scrape_parser.add_argument("--db", help="optional existing CineMyMovies SQLite path")
    scrape_parser.set_defaults(func=scrape)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line program."""
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        return int(args.func(args))
    except (ValueError, RuntimeError, requests.RequestException) as exc:
        LOG.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
