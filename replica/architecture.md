# Architecture: CineStream Rebuild (a clean-room rebuild of YoMovies' core features)

A modern, ad-free streaming catalog and media discovery portal delivering instant playback, multi-server resilience, and fast debounced search without predatory redirects or unauthorized media hosting.

## Stack

| layer | choice | why |
| --- | --- | --- |
| web | Next.js 14+ (App Router) + TypeScript + React | Server-side rendering for instant SEO movie pages, streaming server responses, and type-safe routing |
| styling | Vanilla CSS / Tailwind CSS with design tokens from replica-design | Fluid responsive layouts, dark/AMOLED theme, smooth transitions, and zero runtime CSS overhead |
| database | PostgreSQL on Supabase or Neon | Relational integrity for TV series hierarchy, native `pg_trgm` fuzzy text search, and built-in connection pooling |
| ORM | Drizzle ORM | Zero-overhead, type-safe SQL-first query builder with fast cold-starts and clean migration workflow |
| auth | Guest-first anonymous UUID with optional Supabase Auth / Auth.js | Frictionless immediate access (no sign-up required to watch or bookmark) with optional OAuth sync |
| player | HLS.js + Sandboxed Multi-Server iframe container | Universal device playback support, auto fallback between servers, and strict sandbox isolation against ads |
| jobs | Vercel Cron / Inngest | Periodic TMDb metadata synchronisation, automated server health pings, and broken link report processing |
| storage | Supabase Storage or Cloudflare R2 | Zero-egress cost high-speed CDN distribution for poster art and backdrop images |
| hosting | Vercel | Global edge CDN caching for catalog browse screens, serverless API execution, and zero-downtime deployments |

## Schema

Tables: 12. Access rules: Row Level Security (RLS) on Postgres with client-id isolation for personal watchlists and public read for the media directory.

Full SQL schema is documented in [replica/schema.sql](file:///c:/Users/Singh/Downloads/new-me/replica/schema.sql).

### Key Entities Summary
1. `media_items`: Movies and TV series catalog metadata (slug, title, year, IMDb rating, synopsis, poster/backdrop URLs).
2. `genres`: Taxonomy categories (Action, Drama, Comedy, Sci-Fi, etc.).
3. `media_genres`: Many-to-many relationship linking media items to genres.
4. `languages`: Audio tracks and dubbing tags (Hindi, English, Dual Audio, Tamil, etc.).
5. `media_languages`: Many-to-many relationship mapping audio tracks to media items.
6. `seasons`: TV series season breakdown (series_id, season_number, title, poster_url).
7. `episodes`: TV episodes (season_id, episode_number, title, still_url, air_date, runtime).
8. `video_servers`: Playback stream endpoints with quality labels and priority ordering.
9. `download_links`: Resolution-tagged file download mirrors with size attributes.
10. `watchlists`: User/client bookmark queue with watched status toggle.
11. `issue_reports`: User-submitted broken link reports and playback error logs.
12. `title_requests`: Public user requests for missing titles with community upvoting.

## API

| method path | does | who | input | output | flow |
| --- | --- | --- | --- | --- | --- |
| `GET /api/media/featured` | Returns hero banner spotlight titles | Public | `{ limit?: number }` | `MediaItem[]` | F01 (S01 Discover) |
| `GET /api/media/trending` | Returns top trending carousel items | Public | `{ limit?: number, timeframe?: 'day'\|'week' }` | `MediaItem[]` | F01 (S01 Discover) |
| `GET /api/media` | Paginated catalog listing with multi-facet filters | Public | `query: { type, genre, year, quality, lang, sort, page }` | `{ items: MediaItem[], page: number, totalPages: number }` | F02 (S02/S03 Filter) |
| `GET /api/search/live` | Sub-50ms debounced autocomplete search | Public | `query: { q: string, limit?: number }` | `Array<{ id, title, slug, year, rating, poster, type }>` | F01 (S04 Autocomplete) |
| `GET /api/search` | Full search result page lookup | Public | `query: { q: string, page?: number }` | `{ items: MediaItem[], total: number }` | F01 (S04 Search) |
| `GET /api/media/:slug` | Full title details, active servers, download links | Public | `params: { slug: string }` | `{ media: MediaItem, genres: Genre[], servers: VideoServer[], downloads: DownloadLink[], seasons?: Season[] }` | F01 (S05 Movie Detail) |
| `GET /api/series/:slug/seasons/:seasonNumber/episodes/:episodeNumber` | Episode playback streams and next/prev pointers | Public | `params: { slug, seasonNumber, episodeNumber }` | `{ episode: Episode, servers: VideoServer[], nextEpisode: Episode | null, prevEpisode: Episode | null }` | F03 (S07 Episode Player) |
| `GET /api/watchlist` | Fetch client's bookmarked queue | Client | `header: Cookie (client_id) or Bearer Token` | `WatchlistItem[]` | F05 (S09 Watchlist) |
| `POST /api/watchlist/toggle` | Add/remove title from watchlist | Client | `body: { mediaId: string }` | `{ inWatchlist: boolean, mediaId: string }` | F05 (S09 Watchlist) |
| `POST /api/reports` | Submit broken link / stream issue | Public | `body: { mediaId, episodeId?, serverId?, issueType, description }` | `{ success: boolean, reportId: string }` | F04 (S08 Report Modal) |
| `POST /api/requests` | Request unlisted title | Public | `body: { title, releaseYear, mediaType, notes }` | `{ success: boolean, requestId: string }` | S08 Request System |

### Webhooks & Background Jobs
- **Webhooks In:** None required at initial phase (no external billing webhooks).
- **Webhooks Out:** Optional Discord/Telegram staff webhook alerting when a video server receives >3 broken link reports.
- **Jobs:**
  1. `check-server-health` (Every 30 minutes): Pings video server embed headers to detect dead CDN nodes and mark `is_active = false`.
  2. `sync-trending-tmdb` (Daily at 04:00 UTC): Synchronizes latest ratings, trending releases, and poster backdrops via official TMDb API.
  3. `cleanup-stale-reports` (Weekly): Cleans up resolved or stale issue report records older than 30 days.

## The parts that bite

- **Video Embed Sandboxing & Ad Elimination:** Third-party video embed servers often attempt to launch intrusive pop-unders and ad redirects. The playback container must enforce strict iframe sandboxing: `sandbox="allow-scripts allow-same-origin allow-presentation"` while intentionally omitting `allow-top-navigation` and `allow-popups` to completely neutralize invasive ad behavior.
- **Search Latency & Trigram Scaling:** Searching through tens of thousands of movie and TV show titles with fuzzy spelling tolerance can overload the database. We utilize PostgreSQL's `pg_trgm` extension with GIN indexes (`gin_trgm_ops`) and an in-memory 5-minute LRU cache on the Edge API layer for trending queries.
- **TV Series Deep Hierarchy State:** Navigating between seasons and episodes must retain playback history (e.g. remembering which season/episode the user was watching) without breaking browser history or causing page flashes.
- **Client Identity & Watchlist Persistence:** Since the application allows zero-login usage, watchlists are keyed against a persistent secure client cookie (`x-cines-client-id`). When users eventually authenticate with OAuth, a migration function merges anonymous cookie records into their account profile.
- **Rate Limiting on Public Endpoints:** Endpoints like `/api/reports` and `/api/requests` are protected by IP-hash sliding window rate limiters (e.g., Upstash Redis or memory-based token bucket) to prevent spam.

## Build order

### Milestone 1: Vertical Slice (The Core Loop)
- **Screens:** S01 (Homepage minimal discover), S04 (Live search dropdown), S05 (Movie detail & player).
- **Tables:** `media_items`, `video_servers`.
- **Routes:** `GET /api/media/featured`, `GET /api/search/live`, `GET /api/media/:slug`.
- **Outcome:** A working end-to-end flow: open app, type a movie name, click title, switch between Server 1 and Server 2, and start playback.

### Milestone 2: Must-Haves (Catalog, TV Hierarchy & User Utilities)
- **Screens:** S02 (Movies catalog archive with filters), S03 (TV series directory), S06 (Series seasons overview), S07 (Episode watch page with next/prev), S08 (Report broken link modal), S09 (Watchlist page).
- **Tables:** `genres`, `media_genres`, `languages`, `media_languages`, `seasons`, `episodes`, `watchlists`, `issue_reports`.
- **Routes:** `GET /api/media`, `GET /api/series/.../episodes/...`, `POST /api/watchlist/toggle`, `POST /api/reports`.
- **Outcome:** Full multi-attribute filtering, episodic television traversal, user bookmarks, and playback error reporting.

### Milestone 3: Should-Haves (UX Polish & Media Enhancement)
- **Screens:** S10 (Taxonomy index), S11 (Legal / DMCA notice), S05 enhancements.
- **Tables:** `download_links`, `title_requests`.
- **Features:** Theater mode (dim lights), quality-segmented download links accordion, YouTube official trailer modal, related movies recommendation rail, keyboard navigation shortcuts.

### Milestone 4: Fixes from replica-entrepreneur
- Implementation of UX improvements discovered during user sentiment analysis: ad-free clean interface, dark/AMOLED theme, instant load times, and mobile gesture controls.
