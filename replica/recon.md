# Recon map: YoMovies (Responsive Web)

Scope: Streaming aggregator & media discovery catalog (Movies & Web Series catalog, multi-attribute filtering, live search, multi-server video player, TV seasons/episodes picker, watchlists, broken link reporting)  
For: Clean-room rebuilt high-performance media discovery & streaming portal (suitable for personal media servers, indie film streaming platforms, or catalog aggregators without predatory ads or illegal hosting)  
Date: 2026-10-24  

## Sources

| # | source | URL | notes |
| --- | --- | --- | --- |
| 1 | Target Domain | https://yomovies.wine/ | Primary user-requested index domain (Cloudflare/ISP-gated shadow domain) |
| 2 | Active Mirror Networks | https://yomovies.best/, https://yomovies.luxe/ | Active mirror nodes showing live navigation, movie grids, and taxonomy |
| 3 | Core Engine Specs | DooPlay Movie & TV Series CMS Architecture | The underlying architectural blueprint used by YoMovies and DooThemes clones |
| 4 | Streaming Embed Protocols | Standard Vidsrc / Superembed Multi-Server Embed Schemas | Multi-server fallback and iframe player integration pattern |
| 5 | Open Metadata Standard | The Movie Database (TMDb) & IMDb API Specifications | Schema references for cast, seasons, episodes, ratings, and backdrops |

## Core loop

Browse or search high-resolution films and episodic series, select a reliable playback server, and start instant streaming playback in under three clicks without registration.

## Screens

| ID | screen | route / how to reach | purpose | key components | states seen |
| --- | --- | --- | --- | --- | --- |
| S01 | Homepage / Discover | `/` (direct) | Primary entry point to discover trending, latest Bollywood, Hollywood, Hindi-dubbed releases, and recent TV episodes | Sticky Header, Hero Banner Carousel, Trending Carousel, Language Grid Sections, Media Poster Cards, Footer Links | filled, loading skeleton, mobile drawer |
| S02 | Movies Archive & Grid | `/movies` or `/genre/:slug` | Filterable, paginated directory of full-length films | Breadcrumbs, Multi-attribute Filter Bar, 4-6 Column Media Grid, Pagination controls | filled, filtered, loading skeleton, empty results |
| S03 | TV Shows & Web Series Archive | `/tv-shows` or `/series` | Directory of episodic shows featuring season/episode counters | Filter Bar, Show Poster Cards with Season/Episode badges, Pagination | filled, loading, empty results |
| S04 | Live Search & Advanced Filter | `/search?q=...` or Header Search bar | Instant debounced title lookups and multi-facet filtering (Year, Quality, Genre) | Live Autocomplete Dropdown (with thumbnail, title, release year, rating), Full Search Results Grid, Clear Filters button | empty query, debounced loading, results found, zero matches |
| S05 | Movie Detail & Player | `/movie/:slug` | Watch screen for individual movies with multi-server playback, synopsis, and downloads | 16:9 Video Player Container, Server Selector Pills (Server 1..N), Theater Mode toggle, Metadata Grid (IMDb, runtime, release date, cast, genres), Quality Download Table, Related Titles Carousel | playing, server switching, stream error fallback, downloads expanded |
| S06 | TV Series Detail & Seasons Hub | `/series/:slug` | Series overview displaying show synopsis, cast, and interactive season/episode selectors | Backdrop Hero Header, Seasons Accordion/Tabs (Season 1..N), Episode Cards Grid with air dates and still images, Cast List | season 1 default, season switched, trailer modal |
| S07 | TV Episode Watch Page | `/series/:slug/season-:s/episode-:e` | Dedicated player for specific TV episodes with next/previous controls | Video Player, Server Switcher, Previous / Next Episode Floating Buttons, Quick Episode Drawer, Episode Synopsis | playing, episode transition prompt, server error |
| S08 | Broken Link / Request Modal | Modal on S05 / S07 / Header | Allows viewers to report non-working servers, broken audio, or request new content | Modal Dialog, Server Selector Radio, Error Category Dropdown, Details Textarea, Submit button | closed, open, submitting, success toast |
| S09 | User Watchlist / Favorites | `/watchlist` (Header icon) | Personal saved queue of movies and series to watch later (local storage + optional auth) | Tabbed Filter (All, Movies, Series, Watched), Grid of saved Media Cards, Quick Remove button, Empty State graphic | empty state, populated list, item removed toast |
| S10 | Taxonomy Index (Genres / Years) | `/genres`, `/years`, `/countries` | Hub for browsing by specific categories or release periods | Alphabetical Genre Cards, Year Pill Cloud, Item Count Badges | filled |
| S11 | DMCA & Content Policy Notice | `/dmca`, `/disclaimer` | Legal and compliance disclaimer stating content hosting policies and contact form | Prose Policy Document, Takedown Request Form | static filled |

## Flows

```
F01 Search, Select, and Stream a Movie
    S01 (Homepage) -> S04 (Type search keyword in Header) -> S05 (Select title from live dropdown) -> Video Player starts -> (Optional: Switch to Server 2)
    happy path clicks: 3 clicks
    edge: Server 1 fails to load -> auto-suggest or click Server 2; Title not in catalog -> opens S08 Request Modal

F02 Multi-faceted Catalog Filtering
    S01 -> S02 (Movies Archive) -> Select Genre: "Action" + Year: "2024" + Quality: "1080p" -> Filtered Grid re-renders -> S05 (Movie Detail)
    happy path clicks: 4 clicks
    edge: Filter combo returns 0 items -> display "No matches found" with "Reset Filters" CTA

F03 Binge Watching TV Web Series Episodes
    S01 -> S03 (TV Shows) -> S06 (Series Overview) -> Click Season 2 -> Click Episode 3 -> S07 (Episode Watch Page) -> Click "Next Episode" -> S07 (Episode 4)
    happy path clicks: 5 clicks
    edge: Final episode of season reached -> "Next Episode" button transitions to next season or disables gracefully

F04 Report Broken Playback Stream
    S05 or S07 -> Click "Report Issue / Broken Server" -> S08 (Modal pops up with prefilled Title and Active Server) -> Choose reason "Audio out of sync" -> Click Submit -> Receive Toast Confirmation
    happy path clicks: 3 clicks
    edge: Network offline during submission -> show retry banner in modal

F05 Save Title to Watchlist and Access Later
    S01 or S05 -> Click Bookmark Heart icon on card or detail page -> Badge count in header increments -> Click Header Watchlist -> S09 (Watchlist Page)
    happy path clicks: 2 clicks
    edge: Title already in watchlist -> clicking toggles off and displays "Removed from Watchlist" toast
```

## Components

| component | variants | states | used on |
| --- | --- | --- | --- |
| HeaderNav | Default Sticky, Transparent Over-Hero | Normal, Scrolled (solid background), Mobile menu open | All screens |
| SearchBarWithAutocomplete | Header Compact, Mobile Fullscreen, Filter Page Hero | Idle, Typing, Loading spinner, Results open, Clear input | S01, S02, S03, S04 |
| MediaPosterCard | Movie, TV Show (with episode badge), Compact List | Default, Hover (zoom, overlay icons, synopsis preview), Focused | S01, S02, S03, S04, S09 |
| HeroSlider | Single Featured, Multi-slide Carousel | Auto-advancing, Paused on hover, Transitioning | S01 |
| VideoPlayerBox | Standard 16:9, Theater Mode, Picture-in-Picture | Pre-roll / Poster, Playing, Buffering, Paused, Playback Error | S05, S07 |
| ServerSwitcher | Horizontal Pills, Dropdown Select | Active (highlighted glow), Inactive, Loading test ping, Error | S05, S07 |
| QualityBadge | 4K Ultra, 1080p FHD, 720p HD, CAM / Pre-HD | Default solid, Translucent overlay | S01, S02, S03, S05 |
| AudioLanguageBadge | Hindi Dubbed, Dual Audio, Original English, Multi-Audio | Default colored chip | S01, S02, S05 |
| EpisodeSelectorGrid | Thumbnail Cards, Numbered List, Compact Table | Selected, Unwatched, Watched indicator | S06, S07 |
| FilterPillGroup | Single-select, Multi-select dropdown | Active, Inactive, Hover, Clear all | S02, S03, S04 |
| DownloadLinksTable | Compact Accordion, Full Table | Collapsed, Expanded, Link copying / clicked | S05 |
| ModalDialog | Centered Overlay, Bottom Sheet (mobile) | Hidden, Opening animation, Visible, Closing | S08, Trailer on S06 |
| ToastNotification | Success, Warning, Error, Info | Entering, Visible with auto-dismiss timer, Dismissed | All screens |
| EmptyState | Search Zero-State, Watchlist Empty, Error 404 | Default static illustration with CTA button | S02, S04, S09 |
| PaginationControls | Numbered Buttons with Prev/Next, Infinite Scroll trigger | Page active, Page disabled, Loading next page | S02, S03, S04 |

## Inferred data model

```
MediaItem
  id: uuid / integer
  title: string
  slug: string (unique)
  media_type: enum ('movie', 'tv_show')
  synopsis: text
  tagline: string
  release_year: integer
  release_date: date
  runtime_minutes: integer
  imdb_id: string
  tmdb_id: integer
  imdb_rating: decimal(3,1)
  poster_url: string
  backdrop_url: string
  trailer_youtube_id: string
  status: enum ('released', 'ongoing', 'ended', 'upcoming')
  is_featured: boolean
  view_count: integer
  created_at: timestamp
  evidence: S01 homepage cards, S05/S06 detail headers, DooPlay schema
  confidence: high

Genre
  id: integer
  name: string
  slug: string
  evidence: Header taxonomy links, S02 filter dropdowns
  confidence: high

MediaGenre
  media_id: fk -> MediaItem.id
  genre_id: fk -> Genre.id
  evidence: Many-to-many relationship visible on movie tags
  confidence: high

LanguageAudio
  id: integer
  name: string (e.g. "Hindi", "Dual Audio", "English", "Tamil")
  code: string
  evidence: Card badges and filter options
  confidence: high

MediaAudio
  media_id: fk -> MediaItem.id
  language_id: fk -> LanguageAudio.id
  evidence: Badges on cards and detail page metadata
  confidence: high

VideoServer
  id: uuid
  media_id: fk -> MediaItem.id (nullable if tv episode)
  episode_id: fk -> Episode.id (nullable if movie)
  server_name: string (e.g. "Server 1 [VIP]", "Server 2 [FHD]", "Hydrax", "Streamtape")
  embed_url: string
  quality_label: enum ('4K', '1080p', '720p', '480p')
  priority_order: integer
  is_active: boolean
  last_checked_at: timestamp
  evidence: S05 and S07 player server switch buttons
  confidence: high

Season
  id: uuid
  series_id: fk -> MediaItem.id
  season_number: integer
  title: string (e.g. "Season 1")
  overview: text
  poster_url: string
  air_date: date
  evidence: S06 TV show season selector tabs
  confidence: high

Episode
  id: uuid
  season_id: fk -> Season.id
  episode_number: integer
  title: string
  overview: text
  still_url: string
  air_date: date
  runtime_minutes: integer
  evidence: S06 episode grid, S07 episode playback page
  confidence: high

DownloadLink
  id: uuid
  media_id: fk -> MediaItem.id (nullable if episode)
  episode_id: fk -> Episode.id (nullable if movie)
  host_name: string (e.g. "Fast Cloud", "Mega", "Drive")
  url: string
  resolution: string ('1080p', '720p', '480p')
  file_size_bytes: bigint
  quality_type: string ('BluRay', 'WEB-DL', 'HDRip')
  evidence: S05 download tables and accordion links
  confidence: high

IssueReport
  id: uuid
  media_id: fk -> MediaItem.id
  episode_id: fk -> Episode.id (nullable)
  server_id: fk -> VideoServer.id (nullable)
  issue_type: enum ('broken_link', 'audio_mismatch', 'wrong_movie', 'buffering_lag', 'other')
  description: text
  client_hash: string
  status: enum ('pending', 'investigating', 'resolved', 'dismissed')
  created_at: timestamp
  evidence: S08 Broken link report modal
  confidence: high

UserWatchlist
  id: uuid
  client_id_or_user_id: string
  media_id: fk -> MediaItem.id
  added_at: timestamp
  is_watched: boolean
  evidence: Bookmark button on cards and S09 watchlist screen
  confidence: high
```

Relationships:
- `MediaItem 1-n VideoServer` (for movies)
- `MediaItem 1-n Season` (for TV shows)
- `Season 1-n Episode`
- `Episode 1-n VideoServer`
- `MediaItem m-n Genre` (via MediaGenre)
- `MediaItem m-n LanguageAudio` (via MediaAudio)
- `MediaItem 1-n DownloadLink` / `Episode 1-n DownloadLink`
- `MediaItem 1-n IssueReport`

## Feature matrix

See `features.csv`. Must: 15, should: 8, could: 5, skip: 4.

## Out of scope (cannot or should not be cloned)

- **Pirated Media Hosting & Storage:** YoMovies indexes and hotlinks unauthorized third-party video storage. The clone will not host or distribute copyright-infringing content; it uses legal open-licensed media (Blender Open Projects / Big Buck Bunny / Tears of Steel / Public Domain films), legal iframe integrations (YouTube / Vimeo / Cloudflare Stream / HLS test streams), or self-hosted personal media storage (Plex / Jellyfin / S3 bucket).
- **Predatory Malware Ads & Forced Redirects:** Piracy sites rely heavily on malicious pop-unders, interstitial fake download buttons, and deceptive crypto trackers. The clone strictly omits all deceptive advertising in favor of clean UI/UX and optional standard banner slots.
- **Automated ISP Domain Cycling & Anti-Seizure Proxying:** Rotating through `.wine`, `.best`, `.luxe`, `.top` to dodge domain seizures is out of scope for a clean-room software rebuild.
- **Unlicensed Scraped CDN Endpoints:** Scraping protected or tokenized pirate CDNs without permission will not be cloned.

## Size

Screens: 11, flows: 5, entities: 11.  
Hard parts: Responsive multi-server video player embed container with fallback error handling, TV series hierarchy (Series -> Seasons -> Episodes) with stateful episode navigation, live debounced autocomplete search with multi-faceted filtering.  
Size: **M (a few weeks for a polished, responsive web application)**.
