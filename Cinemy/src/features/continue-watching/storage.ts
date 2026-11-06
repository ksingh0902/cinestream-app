import { ContinueWatchingRecord } from './types';

export const CW_KEY_PREFIX = 'cinemymovies_continue_watching:';
export const LEGACY_CW_KEY = 'cinemymovies_continue_watching';

/**
 * Check if localStorage is accessible in the current browser environment.
 */
export function isStorageAvailable(): boolean {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return false;
    const testKey = '__cw_test__';
    window.localStorage.setItem(testKey, testKey);
    window.localStorage.removeItem(testKey);
    return true;
  } catch {
    return false;
  }
}

/**
 * Resolves the exact storage key for the current authenticated user/role.
 * Replicates the exact formula from index.html:
 * - unauthenticated: "cinemymovies_continue_watching:anonymous"
 * - authenticated: "cinemymovies_continue_watching:" + encodeURIComponent(role + ":" + username)
 */
export function resolveContinueWatchingKey(
  username: string | null,
  role: string | null,
  authenticated: boolean
): string {
  if (!authenticated) {
    return `${CW_KEY_PREFIX}anonymous`;
  }
  const scopeRole = String(role || 'viewer');
  const scopeUser = String(username || role || 'viewer');
  const scope = `${scopeRole}:${scopeUser}`;
  return `${CW_KEY_PREFIX}${encodeURIComponent(scope)}`;
}

/**
 * Preserves legacy storage key for viewer accounts on first read.
 * Never exposes or migrates legacy data to administrator accounts.
 */
export function checkAndMigrateLegacyViewerKey(scopedKey: string, role: string | null): void {
  if (!isStorageAvailable()) return;
  if (String(role || '').toLowerCase() === 'viewer') {
    try {
      if (!window.localStorage.getItem(scopedKey)) {
        const legacy = window.localStorage.getItem(LEGACY_CW_KEY);
        if (legacy) {
          window.localStorage.setItem(scopedKey, legacy);
          window.localStorage.removeItem(LEGACY_CW_KEY);
        }
      }
    } catch {
      // Storage quota or security policy exception
    }
  }
}

/**
 * Reads all Continue Watching records from the scoped key.
 * Validates record structures defensively and sorts by updatedAt descending.
 */
export function readContinueWatchingRecords(scopedKey: string): ContinueWatchingRecord[] {
  if (!isStorageAvailable() || !scopedKey) return [];
  try {
    const raw = window.localStorage.getItem(scopedKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    return parsed
      .filter((it): it is ContinueWatchingRecord => {
        return Boolean(
          it &&
          typeof it === 'object' &&
          typeof it.contentId === 'string' &&
          it.contentId.trim().length > 0 &&
          typeof it.currentTime === 'number' &&
          Number.isFinite(it.currentTime) &&
          it.currentTime >= 0
        );
      })
      .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  } catch (err) {
    console.warn('StorageManager read error:', err);
    return [];
  }
}

/**
 * Removes an item from Continue Watching.
 * Replicates the exact Vanilla removal semantics:
 * - For series: removes ALL episodes associated with the canonical series ID.
 * - For movies: removes the specific contentId.
 */
export function removeContinueWatchingRecord(
  scopedKey: string,
  contentId: string,
  targetSeriesId?: string | null
): ContinueWatchingRecord[] {
  if (!isStorageAvailable() || !scopedKey || !contentId) {
    return [];
  }

  try {
    const currentList = readContinueWatchingRecords(scopedKey);

    // Determine target series ID if not explicitly provided
    let seriesIdToDelete = targetSeriesId ? String(targetSeriesId) : null;
    if (!seriesIdToDelete && contentId.startsWith('series_')) {
      const sMatch = contentId.match(/^series_(.+)_s\d+_e\d+$/);
      if (sMatch) {
        seriesIdToDelete = sMatch[1];
      }
    }

    let updatedList: ContinueWatchingRecord[];
    if (seriesIdToDelete) {
      // Delete all records referencing this series
      updatedList = currentList.filter((it) => {
        const itSeriesId = it.series_id ? String(it.series_id) : null;
        const itContentId = it.contentId || '';
        const itMatch = itContentId.match(/^series_(.+)_s\d+_e\d+$/);
        const parsedSeriesId = itMatch ? itMatch[1] : null;

        const isMatch =
          (itSeriesId && itSeriesId === seriesIdToDelete) ||
          (parsedSeriesId && parsedSeriesId === seriesIdToDelete) ||
          (it.is_series && String(it.id) === seriesIdToDelete);

        return !isMatch;
      });
    } else {
      // Delete single movie record
      updatedList = currentList.filter((it) => it.contentId !== contentId);
    }

    window.localStorage.setItem(scopedKey, JSON.stringify(updatedList));
    return updatedList;
  } catch (err) {
    console.warn('StorageManager remove error:', err);
    return [];
  }
}

/**
 * Clears all Continue Watching records in the current user scope.
 */
export function clearAllContinueWatching(scopedKey: string): void {
  if (!isStorageAvailable() || !scopedKey) return;
  try {
    window.localStorage.removeItem(scopedKey);
  } catch {}
}

/**
 * Retrieves a single record by contentId from the scoped key.
 */
export function getContinueWatchingRecord(
  scopedKey: string,
  contentId: string
): ContinueWatchingRecord | null {
  if (!isStorageAvailable() || !scopedKey || !contentId) return null;
  const records = readContinueWatchingRecords(scopedKey);
  return records.find((it) => it.contentId === contentId) || null;
}

/**
 * Saves or updates a Continue Watching record matching existing Vanilla contracts:
 * - Movies completing >= 95% with verified duration are automatically removed.
 * - Series episodes completing on genuine ended event are marked completed.
 * - Caps maximum stored records at 50.
 * - Dispatches 'cinemymovies_cw_update' for same-tab reactivity.
 */
export function saveContinueWatchingRecord(
  scopedKey: string,
  record: ContinueWatchingRecord
): void {
  if (!isStorageAvailable() || !scopedKey || !record || !record.contentId) {
    return;
  }

  try {
    const isSeries = Boolean(
      record.is_series || (record.contentId && record.contentId.startsWith('series_'))
    );

    // 1. Movie 95% completion rule: automatically remove if >= 95% finished
    if (!isSeries && record.hasVerifiedDuration && record.duration && record.duration >= 300) {
      const isCompletedMovie =
        record.currentTime / record.duration >= 0.95 ||
        (record.isCompleted && record.currentTime / record.duration >= 0.95);

      if (isCompletedMovie) {
        removeContinueWatchingRecord(scopedKey, record.contentId);
        window.dispatchEvent(new CustomEvent('cinemymovies_cw_update'));
        return;
      }
    }

    const currentList = readContinueWatchingRecords(scopedKey);
    const validDuration =
      Number.isFinite(record.duration) && (record.duration ?? 0) > 0
        ? Math.floor(record.duration!)
        : null;

    const progressPct =
      validDuration && validDuration > 0
        ? Math.min(100, Math.round((record.currentTime / validDuration) * 100))
        : 0;

    const sanitizedEntry: ContinueWatchingRecord = {
      ...record,
      currentTime: Math.floor(record.currentTime),
      duration: validDuration,
      hasVerifiedDuration: Boolean(record.hasVerifiedDuration && validDuration),
      progressPct,
      updatedAt: Date.now(),
    };

    // Remove existing entry with identical contentId, then prepend sanitized entry
    const filtered = currentList.filter((it) => it.contentId !== record.contentId);
    const updatedList = [sanitizedEntry, ...filtered].slice(0, 50);

    window.localStorage.setItem(scopedKey, JSON.stringify(updatedList));
    window.dispatchEvent(new CustomEvent('cinemymovies_cw_update'));
  } catch (err) {
    console.warn('StorageManager save error:', err);
  }
}


