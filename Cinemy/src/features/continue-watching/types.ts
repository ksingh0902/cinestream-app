/**
 * Continue Watching & Playback Storage Types
 * Authoritative contract matching existing Vanilla StorageManager
 */

export interface ContinueWatchingRecord {
  /** Unique content identifier: movie id (e.g. "14250") or series episode ("series_145_s1_e2") */
  contentId: string;
  /** Catalogue ID */
  id: number | string;
  /** Catalogue Movie ID alias */
  movie_id?: number | string | null;
  /** Canonical parent series ID, or null for movies */
  series_id?: number | string | null;
  /** Title of movie or series */
  title: string;
  /** Poster image URL */
  poster: string | null;
  poster_url?: string | null;
  /** Release year */
  year?: string | number | null;
  /** Whether the item is a series */
  is_series: boolean;
  /** Season number (if series) */
  season?: number | null;
  /** Episode number (if series) */
  episode?: number | null;
  /** Content provider source: yomovies, dooflix, ask4movie, movies7, etc. */
  source: string;
  /** Whether Hindi dubbed audio is flagged */
  is_hindi_dubbed?: boolean;
  /** Observed playback position in seconds */
  currentTime: number;
  /** Total media duration in seconds, or null if unverified / wall-clock */
  duration: number | null;
  /** Whether duration was verified from genuine HTML5/telemetry media events */
  hasVerifiedDuration: boolean;
  /** Stored progress percentage (0-100) */
  progressPct: number;
  /** Whether marked as completed (e.g. genuine ended event for episode) */
  isCompleted: boolean;
  /** Timestamp when completed */
  completedAt?: number | null;
  /** Timestamp when last updated */
  updatedAt: number;
  /** Next episode season if series episode finished */
  nextSeason?: number | null;
  /** Next episode number if series episode finished */
  nextEpisode?: number | null;
  /** Whether the full series was verified as completed */
  isSeriesCompleted?: boolean;
}

/**
 * Normalized display item ready for the Continue Watching row
 */
export interface ContinueWatchingDisplayItem {
  contentId: string;
  id: number | string;
  seriesId: string | null;
  title: string;
  poster: string;
  year?: string | null;
  isSeries: boolean;
  season?: number | null;
  episode?: number | null;
  source: string;
  isHindiDubbed: boolean;
  currentTime: number;
  duration: number | null;
  hasVerifiedDuration: boolean;
  /** Computed display percentage (0-100) */
  displayProgressPct: number;
  /** Human-readable time or status text: "S1:E2 · 14m left", "Up Next: S1:E3", "1:24:10" */
  metaText: string;
  /** Target season for playback resume */
  targetSeason?: number | null;
  /** Target episode for playback resume */
  targetEpisode?: number | null;
  /** Whether this is an "Up Next" episode recommendation */
  isUpNext: boolean;
  updatedAt: number;
}

