import { WatchlistItem } from './types';

export const WATCHLIST_KEY_PREFIX = 'cinemymovies_watchlist:';
export const WATCHLIST_UPDATE_EVENT = 'cinemymovies_watchlist_update';

function isStorageAvailable(): boolean {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return false;
    const testKey = '__wl_test__';
    window.localStorage.setItem(testKey, testKey);
    window.localStorage.removeItem(testKey);
    return true;
  } catch {
    return false;
  }
}

/**
 * Resolves account-scoped localStorage key for Watchlist.
 * Ensures strict isolation between viewer, admin, and guest/anonymous.
 */
export function resolveWatchlistKey(
  username: string | null,
  role: string | null,
  authenticated: boolean
): string {
  if (!authenticated) {
    return `${WATCHLIST_KEY_PREFIX}anonymous`;
  }
  const scopeRole = String(role || 'viewer');
  const scopeUser = String(username || role || 'viewer');
  const scope = `${scopeRole}:${scopeUser}`;
  return `${WATCHLIST_KEY_PREFIX}${encodeURIComponent(scope)}`;
}

/**
 * Reads all Watchlist items for the scoped account.
 */
export function readWatchlistRecords(scopedKey: string): WatchlistItem[] {
  if (!isStorageAvailable() || !scopedKey) return [];
  try {
    const raw = window.localStorage.getItem(scopedKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    return parsed
      .filter((it): it is WatchlistItem => {
        return Boolean(
          it &&
          typeof it === 'object' &&
          typeof it.id === 'number' &&
          Number.isFinite(it.id) &&
          it.id > 0 &&
          typeof it.title === 'string' &&
          it.title.trim().length > 0
        );
      })
      .sort((a, b) => (b.addedAt || 0) - (a.addedAt || 0));
  } catch (err) {
    console.warn('Watchlist read error:', err);
    return [];
  }
}

/**
 * Adds an item to the scoped account's Watchlist (prevents duplicates).
 */
export function addToWatchlist(scopedKey: string, item: Omit<WatchlistItem, 'addedAt'>): boolean {
  if (!isStorageAvailable() || !scopedKey) return false;
  try {
    const current = readWatchlistRecords(scopedKey);
    // Remove if already exists so it jumps to top
    const filtered = current.filter((it) => it.id !== item.id);
    const newItem: WatchlistItem = {
      ...item,
      addedAt: Date.now(),
    };
    filtered.unshift(newItem);

    // Keep up to 200 items in watchlist
    const trimmed = filtered.slice(0, 200);
    window.localStorage.setItem(scopedKey, JSON.stringify(trimmed));

    window.dispatchEvent(new CustomEvent(WATCHLIST_UPDATE_EVENT, { detail: { id: item.id, action: 'add' } }));
    return true;
  } catch (err) {
    console.warn('Watchlist write error:', err);
    return false;
  }
}

/**
 * Removes an item from the scoped account's Watchlist.
 */
export function removeFromWatchlist(scopedKey: string, id: number): boolean {
  if (!isStorageAvailable() || !scopedKey) return false;
  try {
    const current = readWatchlistRecords(scopedKey);
    const filtered = current.filter((it) => it.id !== id);
    window.localStorage.setItem(scopedKey, JSON.stringify(filtered));

    window.dispatchEvent(new CustomEvent(WATCHLIST_UPDATE_EVENT, { detail: { id, action: 'remove' } }));
    return true;
  } catch (err) {
    console.warn('Watchlist remove error:', err);
    return false;
  }
}

/**
 * Checks if a movie/series is currently saved in the scoped account's Watchlist.
 */
export function isItemInWatchlist(scopedKey: string, id: number): boolean {
  if (!isStorageAvailable() || !scopedKey) return false;
  const current = readWatchlistRecords(scopedKey);
  return current.some((it) => it.id === id);
}

