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
}

export interface CatalogResponse {
  total: number;
  page: number;
  per_page: number;
  items: MovieItem[];
  has_more: boolean;
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
  sort?: 'recent' | 'imdb' | 'rating' | 'title';
  source?: string;
  genre?: string;
  year?: string;
  series?: 0 | 1;
  q?: string;
}

export type CategoryKey = 'all' | 'movies' | 'series' | 'punjabi' | 'hindi-dubbed' | 'hollywood' | 'animation';

