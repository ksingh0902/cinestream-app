export type PlayerState =
  | 'closed'
  | 'opening'
  | 'resolving'
  | 'loading'
  | 'playing'
  | 'paused'
  | 'buffering'
  | 'error'
  | 'ended';

export interface StreamServer {
  label: string;
  url: string;
  kind: 'hls' | 'iframe';
}

export interface StreamInfo {
  kind: 'hls' | 'iframe';
  url: string;
  servers: StreamServer[];
  headers?: Record<string, string>;
  cached?: boolean;
  type?: string;
  play?: string;
  movie_id?: number;
  season?: number | null;
  episode?: number | null;
}

export interface PlaybackTarget {
  id: number | string;
  title: string;
  year?: string | null;
  poster?: string | null;
  isSeries?: boolean;
  season?: number | null;
  episode?: number | null;
  resumeTime?: number;
  source?: string;
  isHindiDubbed?: boolean;
  canonicalSeriesId?: string | null;
  duration_s?: number | null;
  rating?: string | number | null;
  quality?: string | null;
  genres?: string[] | string | null;
  synopsis?: string | null;
}

export interface PlayerMediaTelemetry {
  currentTime: number;
  duration: number | null;
  hasVerifiedDuration: boolean;
  isPaused: boolean;
  isEnded: boolean;
  isBuffering: boolean;
}

export interface SubtitleTrack {
  id: string;
  label: string;
  src: string;
  srclang: string;
  default?: boolean;
}

export interface EpisodeItem {
  episode_number: number;
  name: string;
  s: number;
  e: number;
  movie_id?: number | string | null;
  overview?: string;
}

export type SeriesSeason = SeasonItem;
export type SeriesEpisode = EpisodeItem;

export interface SeasonItem {
  season_number: number;
  name: string;
  episode_count: number;
  episodes: EpisodeItem[];
}

export interface SeriesSeasonResponse {
  is_series: boolean;
  title: string;
  current_season: number;
  current_episode: number;
  seasons: SeasonItem[];
  status?: string;
  is_ended?: boolean;
}

export interface NextEpisodeInfo {
  hasNext: boolean;
  season: number;
  episode: number;
  movieId?: number | string | null;
  name: string;
  label: string;
  fullTitle: string;
  isFinalOfSeries: boolean;
}

export interface PreviousEpisodeInfo {
  hasPrev: boolean;
  season: number;
  episode: number;
  movieId?: number | string | null;
  name: string;
  label: string;
  fullTitle: string;
}


