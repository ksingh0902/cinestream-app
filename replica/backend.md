# Backend Specification: CineStream (YoMovies Clean-Room Rebuild)

Backend architecture, PostgreSQL schema migrations, API routes, sessions, security verification, and integration documentation.

---

## 1. Architecture & Stack Overview

- **Server Runtime:** Node.js HTTP REST API & Static Asset Server (`server/index.js`)
- **Database Engine:** PostgreSQL (Supabase / Neon / Local Postgres) with connection pooling (`pg.Pool`) and seamless in-memory fallback for immediate zero-config execution.
- **Session Layer:** Frictionless anonymous client sessions via secure `HttpOnly` `SameSite=Lax` cookies (`cinestream_client_id`) with persistent watchlist state.
- **Migration & Seed Tools:** Automated runner in `server/migrate.js` applying `replica/schema.sql`, and seeder in `server/seed.js`.

---

## 2. API Routes Implemented

| Method & Route | Functionality | Auth / Access | Input | Output |
| --- | --- | --- | --- | --- |
| `GET /api/media/featured` | Spotlight hero titles | Public | None | `MediaItem[]` |
| `GET /api/media/trending` | Weekly top trending titles | Public | None | `MediaItem[]` |
| `GET /api/media` | Paginated catalog listing with multi-facet filters | Public | `query: { type, genre, language, quality, sort, page, limit }` | `{ items: MediaItem[], total, page, totalPages }` |
| `GET /api/search/live` | Sub-50ms debounced live autocomplete | Public | `query: { q }` | `Array<{ id, title, slug, year, rating, quality, poster, type }>` |
| `GET /api/search` | Comprehensive catalog search results | Public | `query: { q }` | `{ items: MediaItem[], total }` |
| `GET /api/media/:slug` | Movie / Show details with active servers & downloads | Public | `params: { slug }` | `MediaItem` |
| `GET /api/series/:slug/seasons/:s/episodes/:e` | Episode stream metadata & next/prev navigation | Public | `params: { slug, s, e }` | `{ series, season, episode, nextEpisode, prevEpisode }` |
| `GET /api/watchlist` | Fetch client-isolated watchlist queue | Client (Cookie) | None | `MediaItem[]` |
| `POST /api/watchlist/toggle` | Add/remove title from personal watchlist | Client (Cookie) | `body: { mediaId }` | `{ inWatchlist: boolean, mediaId }` |
| `POST /api/reports` | Submit broken streaming link / audio sync issue | Public (Rate Limited) | `body: { mediaTitle, serverName, category, details }` | `{ success: true, reportId }` |
| `POST /api/requests` | Submit request for unlisted title | Public (Rate Limited) | `body: { title, year, notes }` | `{ success: true, requestId }` |
| `POST /api/cron/check-servers` | Automated CDN server health monitoring job | Internal / Cron | None | `{ timestamp, checkedCount, healthyCount, status }` |

---

## 3. Database & Migrations

- **Schema File:** [replica/schema.sql](file:///c:/Users/Singh/Downloads/new-me/replica/schema.sql)
- **Migration Command:** `npm run migrate`
- **Seeding Command:** `npm run seed`
- **Table Count:** 12 tables covering `media_items`, `genres`, `media_genres`, `languages`, `media_languages`, `seasons`, `episodes`, `video_servers`, `download_links`, `watchlists`, `issue_reports`, and `title_requests`.
- **Row Level Security (RLS):** Enabled across all tables in PostgreSQL with client-id isolation on personal watchlists and public read for the media directory.

---

## 4. Official Integrations

- **The Movie Database (TMDb):** Official v3 API integration for automated daily rating syncs, backdrop art, and trending metadata. (Requires user's own API key in `TMDB_API_KEY`).
- **YouTube Official Player API:** Sandboxed iframe embeds for movie/series trailers using official embed domains (`www.youtube.com/embed/...`).
- **HLS / Open Media Streams:** Clean-room test video streams provided via open-source Creative Commons test films (Big Buck Bunny, Tears of Steel, Sintel, Elephants Dream) and standard HTML5 video elements. Zero pirated CDN scraping or unauthorized hotlinking.

---

## 5. Security Checklist

- [x] **Secrets in env vars only:** `.env.example` created without secrets; `.env*` added to `.gitignore`.
- [x] **Input validated on server:** Strings sanitized, lengths capped, HTML tags stripped, JSON bodies size-limited to 1MB.
- [x] **Client data isolation:** Watchlists partitioned by client cookie (`cinestream_client_id`) with RLS enforcement on Supabase.
- [x] **Rate limiting active:** Sliding window token bucket applied to `POST /api/reports` (max 10/min) and `POST /api/requests` (max 5/min).
- [x] **Adware and popup elimination:** Iframe player sandboxing strictly excludes `allow-top-navigation` and `allow-popups`.
- [x] **Security response headers:** `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`.
- [x] **No sensitive user data in logs or URLs.**
- [x] **Dependencies audited:** `npm audit` executed with **0 vulnerabilities**.
- [x] **Compliance & Legal Notice:** DMCA takedown notice submission endpoint and policy published at `/dmca`.
