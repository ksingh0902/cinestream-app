import { apiClient } from './client';
import {
  CatalogFilterParams,
  CatalogResponse,
  DiscoveryResponse,
  EvergreenResponse,
  HomepagePreferences,
  MovieItem,
  RecommendedResponse,
  SearchResponse,
  TrendingResponse,
  YearsResponse,
} from '../types/catalogue';

const STATIC_META_TTL_MS = 60_000;
const staticMetaCache = new Map<string, { expiresAt: number; promise: Promise<any> }>();

function cachedStaticGet<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  const now = Date.now();
  const hit = staticMetaCache.get(key);
  if (hit && hit.expiresAt > now) {
    return hit.promise as Promise<T>;
  }
  const promise = fetcher().catch((err) => {
    staticMetaCache.delete(key);
    throw err;
  });
  staticMetaCache.set(key, { expiresAt: now + STATIC_META_TTL_MS, promise });
  return promise;
}

/**
 * Fetches the static list of supported genres from GET /api/genres (deduped & cached 60s)
 */
export async function getGenres(): Promise<string[]> {
  return cachedStaticGet('genres', () => apiClient.get<string[]>('/api/genres'));
}

/**
 * Queries the catalogue using the existing GET /api/movies endpoint.
 */
export async function getMovies(params: CatalogFilterParams = {}): Promise<CatalogResponse> {
  const query = new URLSearchParams();

  if (params.page !== undefined) query.set('page', String(params.page));
  if (params.per_page !== undefined) query.set('per_page', String(params.per_page));
  if (params.sort) query.set('sort', params.sort);
  if (params.source) query.set('source', params.source);
  if (params.genre) query.set('genre', params.genre);
  if (params.year) query.set('year', params.year);
  if (params.quality) query.set('quality', params.quality);
  if (params.language) query.set('language', params.language);
  if (params.window_months !== undefined) query.set('window_months', String(params.window_months));
  if (params.series !== undefined) query.set('series', String(params.series));
  if (params.q) query.set('q', params.q.trim());

  const qs = query.toString();
  return apiClient.get<CatalogResponse>(`/api/movies${qs ? `?${qs}` : ''}`);
}

/**
 * Discovery Row: Titles first discovered within configured window (GET /api/catalog/recently-added)
 */
export async function getRecentlyAdded(params: { limit?: number; window_months?: number; series?: number; latest_crawl?: boolean } = {}): Promise<DiscoveryResponse> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.window_months !== undefined) query.set('window_months', String(params.window_months));
  if (params.series !== undefined) query.set('series', String(params.series));
  if (params.latest_crawl !== undefined) query.set('latest_crawl', params.latest_crawl ? 'true' : 'false');
  const qs = query.toString();
  return apiClient.get<DiscoveryResponse>(`/api/catalog/recently-added${qs ? `?${qs}` : ''}`);
}

/**
 * Discovery Row: Titles with verified quality improvement within configured window (GET /api/catalog/recently-upgraded)
 */
export async function getRecentlyUpgraded(params: { limit?: number; window_months?: number; series?: number } = {}): Promise<DiscoveryResponse> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.window_months !== undefined) query.set('window_months', String(params.window_months));
  if (params.series !== undefined) query.set('series', String(params.series));
  const qs = query.toString();
  return apiClient.get<DiscoveryResponse>(`/api/catalog/recently-upgraded${qs ? `?${qs}` : ''}`);
}

/**
 * Discovery Row: Trending Now (GET /api/discovery/trending)
 */
export async function getTrending(params: { limit?: number; window_days?: number } = {}): Promise<TrendingResponse> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.window_days !== undefined) query.set('window_days', String(params.window_days));
  const qs = query.toString();
  return apiClient.get<TrendingResponse>(`/api/discovery/trending${qs ? `?${qs}` : ''}`);
}

/**
 * Discovery Row: Evergreen Picks (GET /api/discovery/evergreen)
 */
export async function getEvergreen(params: {
  limit?: number;
  exclude_ids?: number[];
} = {}): Promise<EvergreenResponse> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.exclude_ids && params.exclude_ids.length > 0) {
    query.set('exclude_ids', params.exclude_ids.slice(0, 50).join(','));
  }
  const qs = query.toString();
  return apiClient.get<EvergreenResponse>(`/api/discovery/evergreen${qs ? `?${qs}` : ''}`);
}

/**
 * Discovery Row: Recommended for You (GET /api/discovery/recommended)
 */
export async function getRecommended(params: {
  limit?: number;
  seed_ids?: number[];
  exclude_ids?: number[];
} = {}): Promise<RecommendedResponse> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.seed_ids && params.seed_ids.length > 0) {
    query.set('seed_ids', params.seed_ids.slice(0, 50).join(','));
  }
  if (params.exclude_ids && params.exclude_ids.length > 0) {
    query.set('exclude_ids', params.exclude_ids.slice(0, 50).join(','));
  }
  const qs = query.toString();
  return apiClient.get<RecommendedResponse>(`/api/discovery/recommended${qs ? `?${qs}` : ''}`);
}

/**
 * Release year metadata and title counts (GET /api/catalog/years, deduped & cached 60s)
 */
export async function getCatalogYears(): Promise<YearsResponse> {
  return cachedStaticGet('catalog-years', () => apiClient.get<YearsResponse>('/api/catalog/years'));
}

/**
 * Homepage discovery section preferences (GET /api/homepage/preferences, deduped & cached 60s)
 */
export async function getHomepagePreferences(): Promise<HomepagePreferences> {
  return cachedStaticGet('homepage-preferences', () => apiClient.get<HomepagePreferences>('/api/homepage/preferences'));
}

/**
 * Save homepage discovery section preferences (POST /api/admin/homepage/preferences)
 */
export async function updateHomepagePreferences(prefs: Partial<HomepagePreferences>): Promise<{ ok: boolean; preferences: HomepagePreferences }> {
  return apiClient.post<{ ok: boolean; preferences: HomepagePreferences }>('/api/admin/homepage/preferences', prefs);
}

/**
 * Instant search suggestion dropdown query using GET /api/search
 */
export async function searchTitles(q: string, limit: number = 8): Promise<SearchResponse> {
  const trimmed = q.trim();
  if (!trimmed) {
    return { total: 0, has_more: false, items: [] };
  }
  const query = new URLSearchParams({
    q: trimmed,
    limit: String(limit),
  });
  return apiClient.get<SearchResponse>(`/api/search?${query.toString()}`);
}

/**
 * Retrieves a single movie / series metadata using GET /api/movie/{id}
 */
export async function getMovie(id: number | string): Promise<MovieItem> {
  return apiClient.get<MovieItem>(`/api/movie/${id}`);
}

/**
 * Probe API liveness using GET /api/health
 */
export async function getHealth(): Promise<{ ok: boolean; catalogue: string; time: number }> {
  return apiClient.get<{ ok: boolean; catalogue: string; time: number }>('/api/health');
}

const posterResolveSessionCache = new Map<string, Promise<string | null>>();

/**
 * Bounded, session-cached on-demand poster resolver (GET /api/poster/resolve).
 * Called ONLY when a card's primary poster and DB mirror fallbacks all fail to load.
 */
export function resolvePosterFallback(params: {
  title: string;
  year?: string | null;
  is_series?: boolean | number;
}): Promise<string | null> {
  const title = (params.title || '').trim();
  if (!title) return Promise.resolve(null);
  const year = (params.year || '').trim();
  const isSeries = params.is_series ? 1 : 0;
  const cacheKey = `${title.toLowerCase()}|${year}|${isSeries}`;

  const existing = posterResolveSessionCache.get(cacheKey);
  if (existing) return existing;

  const query = new URLSearchParams({ title, is_series: String(isSeries) });
  if (year) query.set('year', year);

  const req = apiClient
    .get<{ poster_url: string | null; source: string }>(`/api/poster/resolve?${query.toString()}`)
    .then((res) => (res && typeof res.poster_url === 'string' && res.poster_url.trim() ? res.poster_url.trim() : null))
    .catch(() => null);

  posterResolveSessionCache.set(cacheKey, req);
  return req;
}

const backdropResolveSessionCache = new Map<string, Promise<string | null>>();

/**
 * Bounded, session-cached widescreen HD backdrop resolver (GET /api/backdrop/resolve).
 * Used by FeaturedHero to display crisp 16:9 w1280 artwork instead of stretched portrait posters.
 */
export function resolveBackdrop(params: {
  title: string;
  year?: string | null;
  is_series?: boolean | number;
  tmdb_id?: string | number | null;
}): Promise<string | null> {
  const title = (params.title || '').trim();
  const tmdbId = params.tmdb_id != null ? String(params.tmdb_id).trim() : '';
  if (!title && !tmdbId) return Promise.resolve(null);
  const year = (params.year || '').trim();
  const isSeries = params.is_series ? 1 : 0;
  const cacheKey = `${title.toLowerCase()}|${year}|${isSeries}|${tmdbId}`;

  const existing = backdropResolveSessionCache.get(cacheKey);
  if (existing) return existing;

  const query = new URLSearchParams({ title, is_series: String(isSeries) });
  if (year) query.set('year', year);
  if (tmdbId) query.set('tmdb_id', tmdbId);

  const req = apiClient
    .get<{ backdrop_url: string | null; source: string }>(`/api/backdrop/resolve?${query.toString()}`)
    .then((res) => (res && typeof res.backdrop_url === 'string' && res.backdrop_url.trim() ? res.backdrop_url.trim() : null))
    .catch(() => null);

  backdropResolveSessionCache.set(cacheKey, req);
  return req;
}
