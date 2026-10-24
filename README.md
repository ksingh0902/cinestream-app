# MyMovies

Personal streaming front-end for yomovies.wine.

## Run
```bash
pip install -r requirements.txt
python run_crawl.py --max-detail 200      # smoke test
python run_crawl.py                       # full catalogue (resumable)
uvicorn server.app:app --reload --port 8000
```

## Why it doesn't break
| Threat | Defence |
|---|---|
| Signed URL expires every 6 h | Only the *embed URL* is stored. Resolved fresh, cached 30 min. Player auto-refreshes the token and resumes at the same timestamp. |
| Upstream embed domain changes | Embed URL is read as an **absolute URL from the page**; if it dies the movie page is re-scraped to rediscover the current host. |
| CDN blocks cross-origin | Everything plays through `/proxy/hls` + `/proxy/seg` on our own origin. Playlists rewritten, `Range` forwarded for seeking. |
| CDN 403s on hotlinking | Browser-like `User-Agent` + host-derived `Referer`/`Origin`. |
| One server is dead | Multiple embed codes per title, tried in order. |
| Site mirror changes | `SITE_MIRRORS` env var, first healthy mirror wins. |
| Crawl interrupted | Idempotent upserts keyed on URL; rerun continues. |

## Config (env)
`SITE_MIRRORS`, `DEFAULT_EMBED_HOST`, `STREAM_TTL`, `CRAWL_DELAY`, `HTTP_TIMEOUT`, `DB_PATH`

## Legal
Metadata, posters and video streams belong to their respective upstream sources.
This project stores no media by default — it proxies streams for personal viewing.
Set a realistic `CRAWL_DELAY` to be a good citizen.
