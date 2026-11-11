import { apiClient } from './client';
import {
  CatalogFilterParams,
  CatalogResponse,
  DiscoveryResponse,
  HomepagePreferences,
  MovieItem,
  SearchResponse,
  YearsResponse,
} from '../types/catalogue';

/**
 * Fetches the static list of supported genres from GET /api/genres
 */
export async function getGenres(): Promise<string[]> {
  return apiClient.get<string[]>('/api/genres');
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
export async function getRecentlyAdded(params: { limit?: number; window_months?: number; series?: number } = {}): Promise<DiscoveryResponse> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.window_months !== undefined) query.set('window_months', String(params.window_months));
  if (params.series !== undefined) query.set('series', String(params.series));
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
 * Release year metadata and title counts (GET /api/catalog/years)
 */
export async function getCatalogYears(): Promise<YearsResponse> {
  return apiClient.get<YearsResponse>('/api/catalog/years');
}

/**
 * Homepage discovery section preferences (GET /api/homepage/preferences)
 */
export async function getHomepagePreferences(): Promise<HomepagePreferences> {
  return apiClient.get<HomepagePreferences>('/api/homepage/preferences');
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
