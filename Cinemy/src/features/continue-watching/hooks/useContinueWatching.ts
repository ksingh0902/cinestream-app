import { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '../../../context/AuthContext';
import { ContinueWatchingRecord, ContinueWatchingDisplayItem } from '../types';
import {
  resolveContinueWatchingKey,
  checkAndMigrateLegacyViewerKey,
  readContinueWatchingRecords,
  removeContinueWatchingRecord,
  clearAllContinueWatching,
} from '../storage';
import { normalizeContinueWatching } from '../normalizers';

export const CW_UPDATE_EVENT = 'cinemymovies_cw_update';

export function useContinueWatching() {
  const { username, role, authenticated } = useAuth();

  // Resolve active storage scope key based strictly on current authentication
  const scopedKey = useMemo(() => {
    return resolveContinueWatchingKey(username, role, authenticated);
  }, [username, role, authenticated]);

  const [records, setRecords] = useState<ContinueWatchingRecord[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Load records from the current scoped key
  const refreshRecords = useCallback(() => {
    // If not authenticated, Continue Watching is scoped to anonymous or empty
    if (!authenticated) {
      setRecords([]);
      setIsLoading(false);
      return;
    }

    checkAndMigrateLegacyViewerKey(scopedKey, role);
    const loaded = readContinueWatchingRecords(scopedKey);
    setRecords(loaded);
    setIsLoading(false);
  }, [scopedKey, role, authenticated]);

  // When auth state or scoped key changes, refresh records and clear stale data immediately
  useEffect(() => {
    setIsLoading(true);
    refreshRecords();
  }, [scopedKey, refreshRecords]);

  // Event listeners for cross-tab and same-tab reactivity
  useEffect(() => {
    const handleStorageEvent = (e: StorageEvent) => {
      if (e.key === scopedKey) {
        refreshRecords();
      }
    };

    const handleCustomUpdate = () => {
      refreshRecords();
    };

    const handleVisibilityOrFocus = () => {
      if (document.visibilityState === 'visible') {
        refreshRecords();
      }
    };

    window.addEventListener('storage', handleStorageEvent);
    window.addEventListener(CW_UPDATE_EVENT, handleCustomUpdate);
    window.addEventListener('focus', handleVisibilityOrFocus);
    document.addEventListener('visibilitychange', handleVisibilityOrFocus);

    return () => {
      window.removeEventListener('storage', handleStorageEvent);
      window.removeEventListener(CW_UPDATE_EVENT, handleCustomUpdate);
      window.removeEventListener('focus', handleVisibilityOrFocus);
      document.removeEventListener('visibilitychange', handleVisibilityOrFocus);
    };
  }, [scopedKey, refreshRecords]);

  // Remove a record and update in-memory state
  const removeItem = useCallback(
    (contentId: string, seriesId?: string | null) => {
      const updated = removeContinueWatchingRecord(scopedKey, contentId, seriesId);
      setRecords(updated);
      window.dispatchEvent(new CustomEvent(CW_UPDATE_EVENT));
    },
    [scopedKey]
  );

  // Clear all records in current scope
  const clearAll = useCallback(() => {
    clearAllContinueWatching(scopedKey);
    setRecords([]);
    window.dispatchEvent(new CustomEvent(CW_UPDATE_EVENT));
  }, [scopedKey]);

  // Normalize display items
  const displayItems = useMemo<ContinueWatchingDisplayItem[]>(() => {
    return normalizeContinueWatching(records);
  }, [records]);

  return {
    records,
    items: displayItems,
    count: displayItems.length,
    isLoading,
    removeItem,
    clearAll,
    refreshRecords,
    scopedKey,
  };
}

