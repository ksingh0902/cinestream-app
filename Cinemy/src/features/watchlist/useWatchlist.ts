import { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '../../context/AuthContext';
import { WatchlistItem } from './types';
import {
  resolveWatchlistKey,
  readWatchlistRecords,
  addToWatchlist,
  removeFromWatchlist,
  isItemInWatchlist,
  WATCHLIST_UPDATE_EVENT,
} from './storage';

export function useWatchlist() {
  const { username, role, authenticated } = useAuth();

  const scopedKey = useMemo(() => {
    return resolveWatchlistKey(username, role, authenticated);
  }, [username, role, authenticated]);

  const [items, setItems] = useState<WatchlistItem[]>(() => {
    return readWatchlistRecords(scopedKey);
  });

  const refresh = useCallback(() => {
    setItems(readWatchlistRecords(scopedKey));
  }, [scopedKey]);

  // Sync on scoped key changes or storage events
  useEffect(() => {
    refresh();

    const handleUpdate = () => {
      refresh();
    };

    window.addEventListener(WATCHLIST_UPDATE_EVENT, handleUpdate);
    window.addEventListener('storage', handleUpdate);

    return () => {
      window.removeEventListener(WATCHLIST_UPDATE_EVENT, handleUpdate);
      window.removeEventListener('storage', handleUpdate);
    };
  }, [scopedKey, refresh]);

  const addItem = useCallback(
    (item: Omit<WatchlistItem, 'addedAt'>) => {
      addToWatchlist(scopedKey, item);
      refresh();
    },
    [scopedKey, refresh]
  );

  const removeItem = useCallback(
    (id: number) => {
      removeFromWatchlist(scopedKey, id);
      refresh();
    },
    [scopedKey, refresh]
  );

  const isInList = useCallback(
    (id: number) => {
      return isItemInWatchlist(scopedKey, id);
    },
    [scopedKey]
  );

  return {
    items,
    itemCount: items.length,
    addItem,
    removeItem,
    isInList,
    refresh,
  };
}

