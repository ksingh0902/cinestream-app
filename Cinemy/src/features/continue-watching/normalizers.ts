import { ContinueWatchingRecord, ContinueWatchingDisplayItem } from './types';
import { getPosterUrl } from '../../utils/formatters';

/**
 * Formats time in seconds to mm:ss or hh:mm:ss.
 * Exact replication of formatTime from index.html.
 */
export function formatTime(sec: number | null | undefined): string {
  if (sec == null || isNaN(sec) || sec < 0) return '0:00';
  const total = Math.floor(sec);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${h}:${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
  }
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

/**
 * Formats remaining duration into human-readable text (e.g. "14m left", "1h 15m left").
 * Exact replication of formatRemaining from index.html.
 */
export function formatRemaining(sec: number | null | undefined): string {
  if (sec == null || isNaN(sec) || sec <= 0) return '';
  const total = Math.floor(sec);
  const m = Math.round(total / 60);
  if (m >= 60) {
    const h = Math.floor(m / 60);
    const remM = m % 60;
    return remM > 0 ? `${h}h ${remM}m left` : `${h}h left`;
  }
  return `${Math.max(1, m)}m left`;
}

/**
 * Normalizes raw Continue Watching records into presentation-ready display items.
 * Strictly respects Vanilla completion rules:
 * - Movies >= 95% or marked isCompleted are filtered out.
 * - Series episodes are collapsed by canonical series ID into exactly 1 card.
 * - The most recently active episode represents the series.
 * - Derived progress is clamped and never fabricated.
 */
export function normalizeContinueWatching(records: ContinueWatchingRecord[]): ContinueWatchingDisplayItem[] {
  if (!Array.isArray(records) || records.length === 0) {
    return [];
  }

  const seriesGroups = new Map<string, ContinueWatchingRecord[]>();
  const movieItems: ContinueWatchingRecord[] = [];

  for (const it of records) {
    const isSeries = Boolean(it.is_series || (it.contentId && it.contentId.startsWith('series_')));
    if (isSeries) {
      const sMatch = it.contentId ? it.contentId.match(/^series_(.+)_s\d+_e\d+$/) : null;
      const sId = String(it.series_id || (sMatch ? sMatch[1] : null) || it.id || 'series');
      if (!seriesGroups.has(sId)) {
        seriesGroups.set(sId, []);
      }
      seriesGroups.get(sId)!.push(it);
    } else {
      // Movies: apply existing 95% completion threshold and removal rules
      const pct = typeof it.progressPct === 'number' ? it.progressPct : 0;
      if (pct < 95 && !it.isCompleted) {
        movieItems.push(it);
      }
    }
  }

  const selectedSeriesItems: ContinueWatchingRecord[] = [];
  for (const [, epList] of seriesGroups.entries()) {
    // Sort episodes in series: most recently updated first
    epList.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
    // Pick the most recently active episode (incomplete preferred, or latest completed)
    const activeEp = epList.find((ep) => !ep.isCompleted) || epList[0];
    if (activeEp) {
      selectedSeriesItems.push(activeEp);
    }
  }

  // Combine active movie items and active series representations, sorted by updatedAt
  const combined = [...movieItems, ...selectedSeriesItems].sort(
    (a, b) => (b.updatedAt || 0) - (a.updatedAt || 0)
  );

  return combined.map((it): ContinueWatchingDisplayItem => {
    const isSeries = Boolean(it.is_series || (it.contentId && it.contentId.startsWith('series_')));
    const timeFormatted = formatTime(it.currentTime);
    const hasRemaining = Boolean(it.duration && it.duration > it.currentTime);
    const remFormatted = hasRemaining ? formatRemaining(it.duration! - it.currentTime) : '';

    let metaText = '';
    let targetSeason: number | null = it.season ?? null;
    let targetEpisode: number | null = it.episode ?? null;
    let isUpNext = false;

    if (isSeries) {
      if (it.isCompleted) {
        if (it.nextSeason && it.nextEpisode) {
          metaText = `Up Next: S${it.nextSeason}:E${it.nextEpisode}`;
          targetSeason = it.nextSeason;
          targetEpisode = it.nextEpisode;
          isUpNext = true;
        } else if (it.isSeriesCompleted) {
          metaText = `S${it.season || 1}:E${it.episode || 1} · Completed`;
        } else {
          metaText = `S${it.season || 1}:E${it.episode || 1} · Watched`;
        }
      } else {
        metaText = `S${it.season || 1}:E${it.episode || 1}${remFormatted ? ` · ${remFormatted}` : ''}`;
      }
    } else {
      metaText = `${timeFormatted}${remFormatted ? ` · ${remFormatted}` : ''}`;
    }

    // Safely derive visual progress percentage
    let displayPct = 0;
    if (it.isCompleted && !it.nextSeason) {
      displayPct = 100;
    } else if (it.hasVerifiedDuration && it.duration && it.duration > 0 && it.currentTime >= 0) {
      displayPct = Math.min(100, Math.max(1, Math.round((it.currentTime / it.duration) * 100)));
    } else if (typeof it.progressPct === 'number' && it.progressPct > 0) {
      displayPct = Math.min(100, Math.max(1, it.progressPct));
    }

    const sMatch = it.contentId ? it.contentId.match(/^series_(.+)_s\d+_e\d+$/) : null;
    const seriesId = isSeries ? String(it.series_id || (sMatch ? sMatch[1] : null) || it.id) : null;

    return {
      contentId: it.contentId,
      id: it.id,
      seriesId,
      title: it.title,
      poster: getPosterUrl(it.poster || it.poster_url, it.title, it.year ? String(it.year) : null),
      year: it.year ? String(it.year) : null,
      isSeries,
      season: it.season ?? null,
      episode: it.episode ?? null,
      source: it.source || 'yomovies',
      isHindiDubbed: Boolean(it.is_hindi_dubbed),
      currentTime: it.currentTime,
      duration: it.duration,
      hasVerifiedDuration: Boolean(it.hasVerifiedDuration),
      displayProgressPct: displayPct,
      metaText,
      targetSeason,
      targetEpisode,
      isUpNext,
      updatedAt: it.updatedAt || 0,
    };
  });
}

