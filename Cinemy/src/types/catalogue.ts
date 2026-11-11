export interface MovieItem {
  id: number;
  title: string;
  year: string | null;
  poster: string | null;
  poster_url?: string | null;
  rating: number | null;
  imdb: string | null;
  quality?: string | null;
  duration?: string | null;
  duration_s?: number | null;
  genres: string[];
  actors?: string[];
  director?: string[];
  country?: string[];
  synopsis?: string | null;
  is_series: number | boolean;
  source: string;
  is_hindi_dubbed: boolean | number;
  detail_url?: string | null;
  player_kind?: 'hls' | 'iframe' | string;
  audio_edition?: string;
  available_source_count?: number;
  first_added_at?: number | null;
  last_quality_upgrade_at?: number | null;
  latest_quality_transition?: string | null;
  best_quality?: string | null;
  upgradeBadge?: string | null;
}

export interface CatalogResponse {
  total: number;
  page: number;
  per_page: number;
  items: MovieItem[];
  has_more: boolean;
}

export interface DiscoveryResponse {
  total: number;
  items: MovieItem[];
  window_months: number;
}

export interface YearCountItem {
  year: string;
  count: number;
}

export interface YearsResponse {
  years: YearCountItem[];
  older_count: number;
}

export interface HomepagePreferences {
  recently_added_enabled: boolean;
  recently_upgraded_enabled: boolean;
  recently_added_window_months: number;
  recently_upgraded_window_months: number;
  default_sort: string;
  allowed_qualities: string[];
}

export interface SearchItem {
  id: number;
  title: string;
  year: string | null;
  poster: string | null;
  quality?: string | null;
  imdb: string | null;
  is_series: number | boolean;
  source: string;
}

export interface SearchResponse {
  total: number;
  has_more: boolean;
  items: SearchItem[];
}

export interface CatalogFilterParams {
  page?: number;
  per_page?: number;
  sort?: 'recent' | 'first_added' | 'newest_added' | 'recently_upgraded' | 'year' | 'quality' | 'imdb' | 'rating' | 'title';
  source?: string;
  genre?: string;
  year?: string;
  quality?: string;
  language?: string;
  window_months?: number;
  series?: 0 | 1;
  q?: string;
}

export type CategoryKey = 'all' | 'movies' | 'series' | 'punjabi' | 'hindi-dubbed' | 'hollywood' | 'animation';
