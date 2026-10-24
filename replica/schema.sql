-- schema.sql: Database schema for YoMovies Clean-Room Rebuild
-- PostgreSQL (compatible with Supabase, Neon, or vanilla Postgres 15+)

-- Enable UUID extension and pg_trgm for fast fuzzy search
create extension if not exists "uuid-ossp";
create extension if not exists "pg_trgm";

--------------------------------------------------------------------------------
-- 1. MEDIA ITEMS (Movies & TV Series)
--------------------------------------------------------------------------------
create table if not exists media_items (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  slug text not null unique,
  media_type text not null check (media_type in ('movie', 'tv_show')),
  synopsis text,
  tagline text,
  release_year integer check (release_year >= 1880 and release_year <= 2100),
  release_date date,
  runtime_minutes integer,
  imdb_id text,
  tmdb_id integer unique,
  imdb_rating numeric(3, 1) default 0.0 check (imdb_rating >= 0.0 and imdb_rating <= 10.0),
  vote_count integer not null default 0,
  poster_url text,
  backdrop_url text,
  trailer_youtube_id text,
  status text not null default 'released' check (status in ('released', 'ongoing', 'ended', 'upcoming')),
  is_featured boolean not null default false,
  view_count integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Search and filter indexes
create index if not exists idx_media_type_year on media_items (media_type, release_year desc);
create index if not exists idx_media_rating on media_items (media_type, imdb_rating desc);
create index if not exists idx_media_views on media_items (view_count desc);
create index if not exists idx_media_featured on media_items (is_featured) where is_featured = true;
create index if not exists idx_media_title_trgm on media_items using gin (title gin_trgm_ops);

--------------------------------------------------------------------------------
-- 2. TAXONOMIES: GENRES & AUDIO LANGUAGES
--------------------------------------------------------------------------------
create table if not exists genres (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  slug text not null unique,
  created_at timestamptz not null default now()
);

create table if not exists media_genres (
  media_id uuid not null references media_items(id) on delete cascade,
  genre_id uuid not null references genres(id) on delete cascade,
  primary key (media_id, genre_id)
);
create index if not exists idx_media_genres_genre on media_genres (genre_id);

create table if not exists languages (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  code text not null unique,
  is_dubbed boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists media_languages (
  media_id uuid not null references media_items(id) on delete cascade,
  language_id uuid not null references languages(id) on delete cascade,
  primary key (media_id, language_id)
);
create index if not exists idx_media_languages_lang on media_languages (language_id);

--------------------------------------------------------------------------------
-- 3. TV SERIES HIERARCHY: SEASONS & EPISODES
--------------------------------------------------------------------------------
create table if not exists seasons (
  id uuid primary key default gen_random_uuid(),
  series_id uuid not null references media_items(id) on delete cascade,
  season_number integer not null,
  title text not null,
  overview text,
  poster_url text,
  air_date date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (series_id, season_number)
);
create index if not exists idx_seasons_series on seasons (series_id, season_number);

create table if not exists episodes (
  id uuid primary key default gen_random_uuid(),
  season_id uuid not null references seasons(id) on delete cascade,
  episode_number integer not null,
  title text not null,
  overview text,
  still_url text,
  air_date date,
  runtime_minutes integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (season_id, episode_number)
);
create index if not exists idx_episodes_season on episodes (season_id, episode_number);

--------------------------------------------------------------------------------
-- 4. STREAMING SERVERS & DOWNLOAD LINKS
--------------------------------------------------------------------------------
create table if not exists video_servers (
  id uuid primary key default gen_random_uuid(),
  media_id uuid references media_items(id) on delete cascade,
  episode_id uuid references episodes(id) on delete cascade,
  server_name text not null,
  embed_url text not null,
  quality_label text not null default '1080p' check (quality_label in ('4K', '1080p', '720p', '480p', 'CAM')),
  priority_order integer not null default 1,
  is_active boolean not null default true,
  last_checked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint server_target_check check (
    (media_id is not null and episode_id is null) or 
    (media_id is null and episode_id is not null)
  )
);
create index if not exists idx_servers_media on video_servers (media_id, priority_order) where is_active = true;
create index if not exists idx_servers_episode on video_servers (episode_id, priority_order) where is_active = true;

create table if not exists download_links (
  id uuid primary key default gen_random_uuid(),
  media_id uuid references media_items(id) on delete cascade,
  episode_id uuid references episodes(id) on delete cascade,
  host_name text not null,
  url text not null,
  resolution text not null check (resolution in ('4K', '1080p', '720p', '480p')),
  file_size_bytes bigint,
  quality_type text not null default 'WEB-DL' check (quality_type in ('BluRay', 'WEB-DL', 'HDRip', 'CAM')),
  created_at timestamptz not null default now(),
  constraint download_target_check check (
    (media_id is not null and episode_id is null) or 
    (media_id is null and episode_id is not null)
  )
);
create index if not exists idx_downloads_media on download_links (media_id);
create index if not exists idx_downloads_episode on download_links (episode_id);

--------------------------------------------------------------------------------
-- 5. USER WATCHLIST & PLAYLISTS
--------------------------------------------------------------------------------
create table if not exists watchlists (
  id uuid primary key default gen_random_uuid(),
  client_id text not null,
  media_id uuid not null references media_items(id) on delete cascade,
  is_watched boolean not null default false,
  added_at timestamptz not null default now(),
  unique (client_id, media_id)
);
create index if not exists idx_watchlist_client on watchlists (client_id, added_at desc);

--------------------------------------------------------------------------------
-- 6. ISSUE REPORTS & USER TITLE REQUESTS
--------------------------------------------------------------------------------
create table if not exists issue_reports (
  id uuid primary key default gen_random_uuid(),
  media_id uuid not null references media_items(id) on delete cascade,
  episode_id uuid references episodes(id) on delete set null,
  server_id uuid references video_servers(id) on delete set null,
  issue_type text not null check (issue_type in ('broken_link', 'audio_mismatch', 'wrong_movie', 'buffering_lag', 'other')),
  description text,
  client_ip_hash text not null,
  status text not null default 'pending' check (status in ('pending', 'investigating', 'resolved', 'dismissed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_reports_status on issue_reports (status, created_at desc);

create table if not exists title_requests (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  release_year integer check (release_year >= 1880 and release_year <= 2100),
  media_type text not null default 'movie' check (media_type in ('movie', 'tv_show')),
  notes text,
  client_ip_hash text not null,
  upvotes integer not null default 1,
  status text not null default 'requested' check (status in ('requested', 'planned', 'fulfilled', 'rejected')),
  created_at timestamptz not null default now()
);
create index if not exists idx_requests_upvotes on title_requests (upvotes desc);

--------------------------------------------------------------------------------
-- 7. ROW LEVEL SECURITY (RLS) POLICIES
--------------------------------------------------------------------------------
alter table media_items enable row level security;
alter table genres enable row level security;
alter table media_genres enable row level security;
alter table languages enable row level security;
alter table media_languages enable row level security;
alter table seasons enable row level security;
alter table episodes enable row level security;
alter table video_servers enable row level security;
alter table download_links enable row level security;
alter table watchlists enable row level security;
alter table issue_reports enable row level security;
alter table title_requests enable row level security;

-- Public Read Policies
create policy "Public can read media items" on media_items for select using (true);
create policy "Public can read genres" on genres for select using (true);
create policy "Public can read media genres" on media_genres for select using (true);
create policy "Public can read languages" on languages for select using (true);
create policy "Public can read media languages" on media_languages for select using (true);
create policy "Public can read seasons" on seasons for select using (true);
create policy "Public can read episodes" on episodes for select using (true);
create policy "Public can read active video servers" on video_servers for select using (is_active = true);
create policy "Public can read download links" on download_links for select using (true);

-- Watchlist isolation by client_id (supports anonymous cookie id or authenticated user id)
create policy "Clients can view their own watchlist" on watchlists
  for select using (client_id = coalesce(auth.uid()::text, current_setting('app.current_client_id', true)));

create policy "Clients can insert into their own watchlist" on watchlists
  for insert with check (client_id = coalesce(auth.uid()::text, current_setting('app.current_client_id', true)));

create policy "Clients can update their own watchlist" on watchlists
  for update using (client_id = coalesce(auth.uid()::text, current_setting('app.current_client_id', true)));

create policy "Clients can delete from their own watchlist" on watchlists
  for delete using (client_id = coalesce(auth.uid()::text, current_setting('app.current_client_id', true)));

-- Public submissions for issues and requests
create policy "Public can submit issue reports" on issue_reports for insert with check (true);
create policy "Public can submit title requests" on title_requests for insert with check (true);
create policy "Public can view title requests" on title_requests for select using (true);
