export interface WatchlistItem {
  id: number;
  title: string;
  year: string | null;
  poster: string | null;
  is_series: boolean;
  rating?: number | null;
  imdb?: string | null;
  genres?: string[];
  quality?: string | null;
  source?: string;
  addedAt: number;
}

