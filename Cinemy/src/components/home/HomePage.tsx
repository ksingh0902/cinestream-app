import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Sparkles, TrendingUp, Flame, ThumbsUp, Film, Tv } from 'lucide-react';
import { CategorySelection } from '../layout/CategoryBar';
import { HomepagePreferences, MovieItem, YearCountItem } from '../../types/catalogue';
import {
  getMovies,
  getRecentlyAdded,
  getRecentlyUpgraded,
  getTrending,
  getEvergreen,
  getRecommended,
  getCatalogYears,
  getHomepagePreferences,
} from '../../api/catalogue';
import { FeaturedHero } from './FeaturedHero';
import {
  ContinueWatchingSection,
  ContinueWatchingDisplayItem,
} from '../../features/continue-watching';
import { DiscoveryRow } from './DiscoveryRow';
import { BrowseByYear } from './BrowseByYear';
import { ContentGrid } from './ContentGrid';
import { CatalogFilterState } from './CatalogFilterBar';
import { LoadingSkeleton } from '../common/LoadingSkeleton';
import { ErrorBanner } from '../common/ErrorBanner';
import { PlaybackTarget, PlayerModal } from '../../features/player';
import { useRouter } from '../../router';
import { useWatchlist } from '../../features/watchlist';
import { useAuth } from '../../context/AuthContext';
import { useLazySection } from '../../hooks/useLazySection';

// Initial horizontal row batch sizes derived from card width (~175px) + smooth scroll buffer
const INITIAL_DISCOVERY_ROW_LIMIT = 18;
const FULL_DISCOVERY_ROW_LIMIT = 50;
const INITIAL_PREVIEW_CATALOG_LIMIT = 36;
const INITIAL_PREVIEW_DISPLAY_LIMIT = 20;

interface HomePageProps {
  activeCategory: CategorySelection;
  onResetCategory: () => void;
  onSelectCategory: (selection: CategorySelection) => void;
  onPlayTarget?: (target: PlaybackTarget) => void;
}

export const HomePage: React.FC<HomePageProps> = ({
  activeCategory,
  onResetCategory,
  onSelectCategory,
  onPlayTarget,
}) => {
  const { navigate } = useRouter();
  const { isInList, addItem, removeItem } = useWatchlist();
  const { username } = useAuth();

  // Admin display preferences
  const [preferences, setPreferences] = useState<HomepagePreferences>({
    recently_added_enabled: true,
    recently_upgraded_enabled: true,
    recently_added_window_months: 3,
    recently_upgraded_window_months: 3,
    default_sort: 'recent',
    allowed_qualities: ['4K', '1080p', '720p', 'HD', 'WEB-DL', 'BluRay'],
  });

  // Discovery row state
  const [recentlyAddedItems, setRecentlyAddedItems] = useState<MovieItem[]>([]);
  const [recentlyUpgradedItems, setRecentlyUpgradedItems] = useState<MovieItem[]>([]);
  const [trendingItems, setTrendingItems] = useState<MovieItem[]>([]);
  const [trendingExpanded, setTrendingExpanded] = useState<boolean>(false);
  const [trendingExpanding, setTrendingExpanding] = useState<boolean>(false);
  const [recommendedItems, setRecommendedItems] = useState<MovieItem[]>([]);
  const [recommendedPersonalized, setRecommendedPersonalized] = useState<boolean>(false);
  const [evergreenExpanded, setEvergreenExpanded] = useState<boolean>(false);
  const [evergreenExpanding, setEvergreenExpanding] = useState<boolean>(false);
  const [catalogYears, setCatalogYears] = useState<YearCountItem[]>([]);
  const [olderYearsCount, setOlderYearsCount] = useState<number>(0);
  const [allMoviesPreview, setAllMoviesPreview] = useState<MovieItem[]>([]);
  const [allSeriesPreview, setAllSeriesPreview] = useState<MovieItem[]>([]);
  const [heroItems, setHeroItems] = useState<MovieItem[]>([]);

  // Independent per-section loading & error states (no all-or-nothing Promise.all gate)
  // Priority 1 (recentlyAdded) starts loading immediately; Priority 2 sections load lazily on approach.
  type SectionKey = 'recentlyAdded' | 'trending' | 'evergreen' | 'recentlyUpgraded' | 'movies' | 'series' | 'years';
  const [sectionLoading, setSectionLoading] = useState<Record<SectionKey, boolean>>({
    recentlyAdded: true,
    trending: false,
    evergreen: false,
    recentlyUpgraded: false,
    movies: false,
    series: false,
    years: false,
  });
  const [sectionError, setSectionError] = useState<Record<SectionKey, string | null>>({
    recentlyAdded: null,
    trending: null,
    evergreen: null,
    recentlyUpgraded: null,
    movies: null,
    series: null,
    years: null,
  });
  const [sectionLoaded, setSectionLoaded] = useState<Record<SectionKey, boolean>>({
    recentlyAdded: false,
    trending: false,
    evergreen: false,
    recentlyUpgraded: false,
    movies: false,
    series: false,
    years: false,
  });

  // Filtered catalogue grid state (for category tabs, search, filters, or See All)
  const RECENTLY_ADDED_SEE_ALL_PAGE_SIZE = 75;
  const DEFAULT_GRID_PAGE_SIZE = 36;
  const [catalogMovies, setCatalogMovies] = useState<MovieItem[]>([]);
  const [totalCatalogCount, setTotalCatalogCount] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [hasMore, setHasMore] = useState<boolean>(false);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);

  // Active filter state
  const [filters, setFilters] = useState<CatalogFilterState>({
    sort: 'recent',
  });

  // Explicit view mode: 'discovery' (default landing rows) vs 'grid' (filtered catalogue)
  const [viewMode, setViewMode] = useState<'discovery' | 'grid'>('discovery');
  const [gridTitle, setGridTitle] = useState<string>('All Titles');

  // Grid loading and error states
  const [gridLoading, setGridLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [paginationError, setPaginationError] = useState<string | null>(null);

  // Local fallback player target state
  const [internalPlayerTarget, setInternalPlayerTarget] = useState<PlaybackTarget | null>(null);
  const isLoadingMoreRef = useRef(false);
  const trendingExpandingRef = useRef(false);
  const evergreenExpandingRef = useRef(false);
  const discoverySeqRef = useRef(0);
  const [discoveryWave, setDiscoveryWave] = useState<number>(0);
  const fetchedSectionsRef = useRef<Set<SectionKey>>(new Set());
  const recentAddedRef = useRef<MovieItem[]>([]);
  const rawMoviesRef = useRef<MovieItem[]>([]);
  const rawSeriesRef = useRef<MovieItem[]>([]);

  // Determine if activeCategory requires grid view
  const isFilteredCategory = Boolean(
    activeCategory.category !== 'all' || activeCategory.genre
  );
  const isDiscoveryActive = viewMode === 'discovery' && !isFilteredCategory;

  // Priority 2: IntersectionObserver triggers for below-the-fold sections (preload 300px ahead)
  const trendingLazy = useLazySection({ enabled: isDiscoveryActive });
  const evergreenLazy = useLazySection({ enabled: isDiscoveryActive });
  const upgradedLazy = useLazySection({ enabled: isDiscoveryActive && preferences.recently_upgraded_enabled });
  const yearsLazy = useLazySection({ enabled: isDiscoveryActive });
  const moviesLazy = useLazySection({ enabled: isDiscoveryActive });
  const seriesLazy = useLazySection({ enabled: isDiscoveryActive });

  // Viewer-identity isolation: clear personalized recommendations when active viewer changes
  const prevUsernameRef = useRef<string | null | undefined>(username);
  useEffect(() => {
    if (prevUsernameRef.current !== username) {
      prevUsernameRef.current = username;
      setRecommendedItems([]);
      setRecommendedPersonalized(false);
      setEvergreenExpanded(false);
      setEvergreenExpanding(false);
      evergreenExpandingRef.current = false;
      fetchedSectionsRef.current.delete('evergreen');
      setSectionLoaded((prev) => ({ ...prev, evergreen: false }));
    }
  }, [username]);

  // Fetch preferences once without triggering duplicate waves when defaults match
  useEffect(() => {
    let active = true;
    getHomepagePreferences()
      .then((p) => {
        if (!active || !p) return;
        setPreferences((prev) => {
          if (
            prev.recently_added_enabled === p.recently_added_enabled &&
            prev.recently_upgraded_enabled === p.recently_upgraded_enabled &&
            prev.recently_added_window_months === p.recently_added_window_months &&
            prev.recently_upgraded_window_months === p.recently_upgraded_window_months &&
            prev.default_sort === p.default_sort
          ) {
            return prev;
          }
          return p;
        });
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const recomputeDerivedPreviews = useCallback(() => {
    const addedList = recentAddedRef.current;
    const addedIds = new Set(addedList.map((m) => m.id));
    const addedTitles = new Set(
      addedList.map((m) => (m.title || '').toLowerCase().replace(/\s*[\[(]\s*(?:19|20)\d{2}\s*[\])]/g, '').trim())
    );

    if (rawMoviesRef.current.length > 0) {
      const moviesPreview = rawMoviesRef.current
        .filter((m) => !addedIds.has(m.id) && !addedTitles.has((m.title || '').toLowerCase().replace(/\s*[\[(]\s*(?:19|20)\d{2}\s*[\])]/g, '').trim()))
        .slice(0, INITIAL_PREVIEW_DISPLAY_LIMIT);
      setAllMoviesPreview(moviesPreview);
    }

    if (rawSeriesRef.current.length > 0) {
      const seriesPreview = rawSeriesRef.current
        .filter((m) => !addedIds.has(m.id) && !addedTitles.has((m.title || '').toLowerCase().replace(/\s*[\[(]\s*(?:19|20)\d{2}\s*[\])]/g, '').trim()))
        .slice(0, INITIAL_PREVIEW_DISPLAY_LIMIT);
      setAllSeriesPreview(seriesPreview);
    }

    const candidateHero = [...addedList, ...rawMoviesRef.current].filter(
      (m) => m.poster && !m.poster.includes('logo.png')
    );
    if (candidateHero.length > 0) {
      const uniqueHero = Array.from(new Map(candidateHero.map((m) => [m.id, m])).values());
      setHeroItems(uniqueHero.slice(0, 6));
    }
  }, []);

  const fetchRecentlyAddedSection = useCallback(
    async (seq: number) => {
      setSectionLoading((prev) => ({ ...prev, recentlyAdded: true }));
      setSectionError((prev) => ({ ...prev, recentlyAdded: null }));
      try {
        const addedRes = await getRecentlyAdded({
          limit: INITIAL_DISCOVERY_ROW_LIMIT,
          window_months: preferences.recently_added_window_months,
          latest_crawl: true,
        });
        if (discoverySeqRef.current !== seq) return;
        const items = addedRes.items || [];
        recentAddedRef.current = items;
        setRecentlyAddedItems(items);
        setSectionLoaded((prev) => ({ ...prev, recentlyAdded: true }));
        recomputeDerivedPreviews();
      } catch (err: any) {
        if (discoverySeqRef.current !== seq) return;
        setSectionError((prev) => ({
          ...prev,
          recentlyAdded: err?.message || 'Unable to load Recently Added.',
        }));
      } finally {
        if (discoverySeqRef.current === seq) {
          setSectionLoading((prev) => ({ ...prev, recentlyAdded: false }));
        }
      }
    },
    [preferences.recently_added_window_months, recomputeDerivedPreviews]
  );

  const fetchTrendingSection = useCallback(async (seq: number) => {
    setSectionLoading((prev) => ({ ...prev, trending: true }));
    setSectionError((prev) => ({ ...prev, trending: null }));
    setTrendingExpanded(false);
    setTrendingExpanding(false);
    trendingExpandingRef.current = false;
    try {
      const trendingRes = await getTrending({ limit: INITIAL_DISCOVERY_ROW_LIMIT });
      if (discoverySeqRef.current !== seq) return;
      const items = trendingRes.items || [];
      setTrendingItems(items);
      if (items.length < INITIAL_DISCOVERY_ROW_LIMIT) {
        setTrendingExpanded(true);
      }
      setSectionLoaded((prev) => ({ ...prev, trending: true }));
    } catch (err: any) {
      if (discoverySeqRef.current !== seq) return;
      setSectionError((prev) => ({
        ...prev,
        trending: err?.message || 'Unable to load Trending Now.',
      }));
    } finally {
      if (discoverySeqRef.current === seq) {
        setSectionLoading((prev) => ({ ...prev, trending: false }));
      }
    }
  }, []);

  // Progressive horizontal load (18 -> 50) when user scrolls near the right edge of Trending
  const handleExpandTrending = useCallback(async () => {
    if (trendingExpanded || trendingExpandingRef.current) return;
    const seq = discoverySeqRef.current;
    trendingExpandingRef.current = true;
    setTrendingExpanding(true);
    try {
      const fullRes = await getTrending({ limit: FULL_DISCOVERY_ROW_LIMIT });
      if (discoverySeqRef.current !== seq) return;
      const fullItems = fullRes.items || [];
      setTrendingItems((prev) => {
        const seen = new Set(prev.map((m) => m.id));
        const extra = fullItems.filter((m) => !seen.has(m.id));
        return extra.length > 0 ? [...prev, ...extra] : prev;
      });
      setTrendingExpanded(true);
    } catch {
      // Keep existing 18 cards intact on expansion error; user can retry by scrolling again
    } finally {
      if (discoverySeqRef.current === seq) {
        setTrendingExpanding(false);
        trendingExpandingRef.current = false;
      }
    }
  }, [trendingExpanded]);

  // Option A: Server-side-only personalization eligibility. Never send device-local seed_ids.
  // If /api/discovery/recommended fails or returns empty, explicitly fall back to /api/discovery/evergreen.
  const fetchEvergreenOrRecommendedSection = useCallback(async (seq: number) => {
    setSectionLoading((prev) => ({ ...prev, evergreen: true }));
    setSectionError((prev) => ({ ...prev, evergreen: null }));
    setEvergreenExpanded(false);
    setEvergreenExpanding(false);
    evergreenExpandingRef.current = false;
    try {
      const recRes = await getRecommended({ limit: INITIAL_DISCOVERY_ROW_LIMIT });
      if (discoverySeqRef.current !== seq) return;
      if (recRes && Array.isArray(recRes.items) && recRes.items.length > 0) {
        setRecommendedItems(recRes.items);
        setRecommendedPersonalized(Boolean(recRes.personalized));
        if (recRes.items.length < INITIAL_DISCOVERY_ROW_LIMIT) {
          setEvergreenExpanded(true);
        }
        setSectionLoaded((prev) => ({ ...prev, evergreen: true }));
        return;
      }
      // Empty response -> fall back to dedicated Evergreen endpoint
      const evRes = await getEvergreen({ limit: INITIAL_DISCOVERY_ROW_LIMIT });
      if (discoverySeqRef.current !== seq) return;
      const evItems = evRes.items || [];
      setRecommendedItems(evItems);
      setRecommendedPersonalized(false);
      if (evItems.length < INITIAL_DISCOVERY_ROW_LIMIT) {
        setEvergreenExpanded(true);
      }
      setSectionLoaded((prev) => ({ ...prev, evergreen: true }));
    } catch {
      if (discoverySeqRef.current !== seq) return;
      try {
        const evRes = await getEvergreen({ limit: INITIAL_DISCOVERY_ROW_LIMIT });
        if (discoverySeqRef.current !== seq) return;
        const evItems = evRes.items || [];
        setRecommendedItems(evItems);
        setRecommendedPersonalized(false);
        if (evItems.length < INITIAL_DISCOVERY_ROW_LIMIT) {
          setEvergreenExpanded(true);
        }
        setSectionLoaded((prev) => ({ ...prev, evergreen: true }));
      } catch (evErr: any) {
        if (discoverySeqRef.current !== seq) return;
        setRecommendedPersonalized(false);
        setSectionError((prev) => ({
          ...prev,
          evergreen: evErr?.message || 'Unable to load Evergreen Picks.',
        }));
      }
    } finally {
      if (discoverySeqRef.current === seq) {
        setSectionLoading((prev) => ({ ...prev, evergreen: false }));
      }
    }
  }, []);

  // Progressive horizontal load (18 -> 50) when user scrolls near the right edge of Evergreen / Recommended
  const handleExpandEvergreen = useCallback(async () => {
    if (evergreenExpanded || evergreenExpandingRef.current) return;
    const seq = discoverySeqRef.current;
    evergreenExpandingRef.current = true;
    setEvergreenExpanding(true);
    try {
      let fullItems: MovieItem[] = [];
      try {
        const recRes = await getRecommended({ limit: FULL_DISCOVERY_ROW_LIMIT });
        if (discoverySeqRef.current !== seq) return;
        if (recRes && Array.isArray(recRes.items) && recRes.items.length > 0) {
          fullItems = recRes.items;
        }
      } catch {
        // Fall through to Evergreen fallback below
      }
      if (fullItems.length === 0) {
        const evRes = await getEvergreen({ limit: FULL_DISCOVERY_ROW_LIMIT });
        if (discoverySeqRef.current !== seq) return;
        fullItems = evRes.items || [];
      }
      setRecommendedItems((prev) => {
        const seen = new Set(prev.map((m) => m.id));
        const extra = fullItems.filter((m) => !seen.has(m.id));
        return extra.length > 0 ? [...prev, ...extra] : prev;
      });
      setEvergreenExpanded(true);
    } catch {
      // Keep existing 18 cards intact on expansion error
    } finally {
      if (discoverySeqRef.current === seq) {
        setEvergreenExpanding(false);
        evergreenExpandingRef.current = false;
      }
    }
  }, [evergreenExpanded]);

  const fetchRecentlyUpgradedSection = useCallback(
    async (seq: number) => {
      setSectionLoading((prev) => ({ ...prev, recentlyUpgraded: true }));
      setSectionError((prev) => ({ ...prev, recentlyUpgraded: null }));
      try {
        const upgradedRes = await getRecentlyUpgraded({
          limit: INITIAL_DISCOVERY_ROW_LIMIT,
          window_months: preferences.recently_upgraded_window_months,
        });
        if (discoverySeqRef.current !== seq) return;
        setRecentlyUpgradedItems(upgradedRes.items || []);
        setSectionLoaded((prev) => ({ ...prev, recentlyUpgraded: true }));
      } catch (err: any) {
        if (discoverySeqRef.current !== seq) return;
        setSectionError((prev) => ({
          ...prev,
          recentlyUpgraded: err?.message || 'Unable to load Recently Upgraded.',
        }));
      } finally {
        if (discoverySeqRef.current === seq) {
          setSectionLoading((prev) => ({ ...prev, recentlyUpgraded: false }));
        }
      }
    },
    [preferences.recently_upgraded_window_months]
  );

  const fetchMoviesSection = useCallback(
    async (seq: number) => {
      setSectionLoading((prev) => ({ ...prev, movies: true }));
      setSectionError((prev) => ({ ...prev, movies: null }));
      try {
        const moviesRes = await getMovies({ per_page: INITIAL_PREVIEW_CATALOG_LIMIT, series: 0, sort: 'recent' });
        if (discoverySeqRef.current !== seq) return;
        rawMoviesRef.current = moviesRes.items || [];
        setSectionLoaded((prev) => ({ ...prev, movies: true }));
        recomputeDerivedPreviews();
      } catch (err: any) {
        if (discoverySeqRef.current !== seq) return;
        setSectionError((prev) => ({
          ...prev,
          movies: err?.message || 'Unable to load Feature Films & Movies.',
        }));
      } finally {
        if (discoverySeqRef.current === seq) {
          setSectionLoading((prev) => ({ ...prev, movies: false }));
        }
      }
    },
    [recomputeDerivedPreviews]
  );

  const fetchSeriesSection = useCallback(
    async (seq: number) => {
      setSectionLoading((prev) => ({ ...prev, series: true }));
      setSectionError((prev) => ({ ...prev, series: null }));
      try {
        const seriesRes = await getMovies({ per_page: INITIAL_PREVIEW_CATALOG_LIMIT, series: 1, sort: 'recent' });
        if (discoverySeqRef.current !== seq) return;
        rawSeriesRef.current = seriesRes.items || [];
        setSectionLoaded((prev) => ({ ...prev, series: true }));
        recomputeDerivedPreviews();
      } catch (err: any) {
        if (discoverySeqRef.current !== seq) return;
        setSectionError((prev) => ({
          ...prev,
          series: err?.message || 'Unable to load Web Series & Television.',
        }));
      } finally {
        if (discoverySeqRef.current === seq) {
          setSectionLoading((prev) => ({ ...prev, series: false }));
        }
      }
    },
    [recomputeDerivedPreviews]
  );

  const fetchYearsSection = useCallback(async (seq: number) => {
    setSectionLoading((prev) => ({ ...prev, years: true }));
    setSectionError((prev) => ({ ...prev, years: null }));
    try {
      const yearsRes = await getCatalogYears();
      if (discoverySeqRef.current !== seq) return;
      setCatalogYears(yearsRes.years || []);
      setOlderYearsCount(yearsRes.older_count || 0);
      setSectionLoaded((prev) => ({ ...prev, years: true }));
    } catch {
      if (discoverySeqRef.current !== seq) return;
      setSectionError((prev) => ({ ...prev, years: 'Unable to load release years.' }));
    } finally {
      if (discoverySeqRef.current === seq) {
        setSectionLoading((prev) => ({ ...prev, years: false }));
      }
    }
  }, []);

  // Priority 1: On initial Home open, ONLY fetch critical first-viewport data (Hero + Recently Added).
  // Below-the-fold sections (Trending, Evergreen/Recommended, Upgraded, Years, Movies, Series) load
  // progressively via IntersectionObserver as the user approaches them.
  const fetchDiscoveryData = useCallback(() => {
    const seq = ++discoverySeqRef.current;
    fetchedSectionsRef.current = new Set<SectionKey>(['recentlyAdded']);
    setError(null);
    setDiscoveryWave(seq);
    void fetchRecentlyAddedSection(seq);
  }, [fetchRecentlyAddedSection]);

  // Priority 2: Lazy-trigger below-the-fold sections exactly once per discovery wave when approaching viewport
  useEffect(() => {
    if (!isDiscoveryActive || discoveryWave === 0) return;
    if (trendingLazy.isTriggered && !fetchedSectionsRef.current.has('trending')) {
      fetchedSectionsRef.current.add('trending');
      void fetchTrendingSection(discoverySeqRef.current);
    }
  }, [isDiscoveryActive, discoveryWave, trendingLazy.isTriggered, fetchTrendingSection]);

  useEffect(() => {
    if (!isDiscoveryActive || discoveryWave === 0) return;
    if (evergreenLazy.isTriggered && !fetchedSectionsRef.current.has('evergreen')) {
      fetchedSectionsRef.current.add('evergreen');
      void fetchEvergreenOrRecommendedSection(discoverySeqRef.current);
    }
  }, [isDiscoveryActive, discoveryWave, username, evergreenLazy.isTriggered, fetchEvergreenOrRecommendedSection]);

  useEffect(() => {
    if (!isDiscoveryActive || discoveryWave === 0 || !preferences.recently_upgraded_enabled) return;
    if (upgradedLazy.isTriggered && !fetchedSectionsRef.current.has('recentlyUpgraded')) {
      fetchedSectionsRef.current.add('recentlyUpgraded');
      void fetchRecentlyUpgradedSection(discoverySeqRef.current);
    }
  }, [isDiscoveryActive, discoveryWave, preferences.recently_upgraded_enabled, upgradedLazy.isTriggered, fetchRecentlyUpgradedSection]);

  useEffect(() => {
    if (!isDiscoveryActive || discoveryWave === 0) return;
    if (yearsLazy.isTriggered && !fetchedSectionsRef.current.has('years')) {
      fetchedSectionsRef.current.add('years');
      void fetchYearsSection(discoverySeqRef.current);
    }
  }, [isDiscoveryActive, discoveryWave, yearsLazy.isTriggered, fetchYearsSection]);

  useEffect(() => {
    if (!isDiscoveryActive || discoveryWave === 0) return;
    if (moviesLazy.isTriggered && !fetchedSectionsRef.current.has('movies')) {
      fetchedSectionsRef.current.add('movies');
      void fetchMoviesSection(discoverySeqRef.current);
    }
  }, [isDiscoveryActive, discoveryWave, moviesLazy.isTriggered, fetchMoviesSection]);

  useEffect(() => {
    if (!isDiscoveryActive || discoveryWave === 0) return;
    if (seriesLazy.isTriggered && !fetchedSectionsRef.current.has('series')) {
      fetchedSectionsRef.current.add('series');
      void fetchSeriesSection(discoverySeqRef.current);
    }
  }, [isDiscoveryActive, discoveryWave, seriesLazy.isTriggered, fetchSeriesSection]);

  // Fetch filtered catalogue grid
  const fetchFilteredGrid = useCallback(
    async (pageToFetch: number = 1, append: boolean = false) => {
      if (pageToFetch === 1) {
        setGridLoading(true);
        setError(null);
      } else {
        setIsLoadingMore(true);
        setPaginationError(null);
      }

      try {
        const seriesParam =
          activeCategory.series !== undefined
            ? activeCategory.series
            : activeCategory.category === 'movies'
            ? 0
            : activeCategory.category === 'series'
            ? 1
            : undefined;

        const effectiveGenre = filters.genre || activeCategory.genre;
        const effectiveSort = (filters.sort as any) || preferences.default_sort || 'recent';
        const isRecentlyAddedGrid = effectiveSort === 'first_added' || effectiveSort === 'newest_added';
        const pageSize = isRecentlyAddedGrid ? RECENTLY_ADDED_SEE_ALL_PAGE_SIZE : DEFAULT_GRID_PAGE_SIZE;

        const res = await getMovies({
          page: pageToFetch,
          per_page: pageSize,
          series: seriesParam,
          genre: effectiveGenre,
          year: filters.year,
          quality: filters.quality,
          language: filters.language,
          sort: effectiveSort,
        });

        const newItems = res.items || [];
        if (append) {
          setCatalogMovies((prev) => {
            const existingIds = new Set(prev.map((m) => m.id));
            const unique = newItems.filter((m) => !existingIds.has(m.id));
            return [...prev, ...unique];
          });
        } else {
          setCatalogMovies(newItems);
        }

        setTotalCatalogCount(res.total || 0);
        setCurrentPage(pageToFetch);
        setHasMore(res.has_more);
      } catch (err: any) {
        if (pageToFetch === 1) {
          setError(err.message || 'Unable to load catalogue titles.');
        } else {
          setPaginationError(err.message || 'Failed to load additional titles.');
        }
      } finally {
        setGridLoading(false);
        setIsLoadingMore(false);
        isLoadingMoreRef.current = false;
      }
    },
    [activeCategory, filters, preferences.default_sort]
  );

  const prevCategoryRef = useRef<CategorySelection>(activeCategory);

  // Sync viewMode and data loading on route or filter changes
  useEffect(() => {
    const prevCat = prevCategoryRef.current;
    const categoryChanged =
      prevCat.category !== activeCategory.category ||
      prevCat.genre !== activeCategory.genre ||
      prevCat.series !== activeCategory.series;
    const hasResetToken = Boolean(
      activeCategory.resetToken && activeCategory.resetToken !== prevCat.resetToken
    );

    prevCategoryRef.current = activeCategory;

    // When navigating to or clicking "All Titles", always restore the discovery homepage
    if (
      (activeCategory.category === 'all' && !activeCategory.genre && (categoryChanged || hasResetToken)) ||
      hasResetToken
    ) {
      setViewMode('discovery');
      setGridTitle('All Titles');
      setFilters({ sort: 'recent' });
      fetchDiscoveryData();
      return;
    }

    if (isFilteredCategory) {
      setViewMode('grid');
      // Set section title
      if (activeCategory.genre) {
        setGridTitle(`${activeCategory.genre} Collection`);
      } else if (activeCategory.category === 'movies') {
        setGridTitle('All Feature Films');
      } else if (activeCategory.category === 'series') {
        setGridTitle('All Web Series & TV Shows');
      } else if (activeCategory.category === 'punjabi') {
        setGridTitle('Punjabi Cinema');
      } else if (activeCategory.category === 'hindi-dubbed') {
        setGridTitle('Hindi Dubbed & Dual Audio');
      } else if (activeCategory.category === 'hollywood') {
        setGridTitle('Hollywood Cinema');
      } else if (activeCategory.category === 'animation') {
        setGridTitle('Animation & Anime');
      } else {
        setGridTitle('Filtered Titles');
      }
      fetchFilteredGrid(1, false);
    } else if (viewMode === 'grid') {
      fetchFilteredGrid(1, false);
    } else if (discoverySeqRef.current === 0) {
      fetchDiscoveryData();
    }
  }, [activeCategory, isFilteredCategory, viewMode, fetchDiscoveryData, fetchFilteredGrid]);

  // Load More pagination
  const handleLoadMore = () => {
    if (isLoadingMoreRef.current || !hasMore) return;
    isLoadingMoreRef.current = true;
    fetchFilteredGrid(currentPage + 1, true);
  };

  // Change individual filter
  const handleChangeFilter = (key: keyof CatalogFilterState, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value || undefined }));
    setViewMode('grid');
  };

  // Clear all filters
  const handleClearFilters = () => {
    setFilters({ sort: 'recent' });
    if (!isFilteredCategory) {
      setViewMode('discovery');
    }
  };

  // Handlers for "See All" actions
  const handleSeeAllRecentlyAdded = () => {
    setFilters({ sort: 'first_added' });
    setGridTitle('Recently Added to CINEMY');
    setViewMode('grid');
  };

  const handleSeeAllRecentlyUpgraded = () => {
    setFilters({ sort: 'recently_upgraded' });
    setGridTitle('Recently Upgraded Quality');
    setViewMode('grid');
  };

  const handleSeeAllMovies = () => {
    onSelectCategory({ category: 'movies', series: 0 });
  };

  const handleSeeAllSeries = () => {
    onSelectCategory({ category: 'series', series: 1 });
  };

  const handleSelectYear = (year: string) => {
    setFilters((prev) => ({ ...prev, year }));
    setGridTitle(year === 'older' ? 'Classic Cinema (Pre-2020)' : `Release Year: ${year}`);
    setViewMode('grid');
  };

  const handleResetToDiscovery = () => {
    handleClearFilters();
    onResetCategory();
    setViewMode('discovery');
    setGridTitle('All Titles');
    fetchDiscoveryData();
  };

  const triggerPlay = (target: PlaybackTarget) => {
    if (onPlayTarget) {
      onPlayTarget(target);
    } else {
      setInternalPlayerTarget(target);
    }
  };

  const handlePlay = (id: number, title: string) => {
    const allTitles = [
      ...heroItems,
      ...recentlyAddedItems,
      ...recentlyUpgradedItems,
      ...allMoviesPreview,
      ...allSeriesPreview,
      ...catalogMovies,
    ];
    const found = allTitles.find((m) => m.id === id);
    const target: PlaybackTarget = {
      id,
      title: found?.title || title,
      year: found?.year,
      poster: found?.poster || found?.poster_url,
      isSeries: Boolean(found?.is_series),
      source: found?.source || 'yomovies',
      isHindiDubbed: Boolean(found?.is_hindi_dubbed),
      duration_s: found?.duration_s,
    };
    triggerPlay(target);
  };

  const handleCardClick = useCallback(
    (id: number, _title: string) => {
      const allTitles = [
        ...heroItems,
        ...recentlyAddedItems,
        ...recentlyUpgradedItems,
        ...trendingItems,
        ...recommendedItems,
        ...allMoviesPreview,
        ...allSeriesPreview,
        ...catalogMovies,
      ];
      const found = allTitles.find((m) => m.id === id);
      if (found?.is_series) {
        navigate(`/series/${id}`);
      } else {
        navigate(`/movie/${id}`);
      }
    },
    [heroItems, recentlyAddedItems, recentlyUpgradedItems, trendingItems, recommendedItems, allMoviesPreview, allSeriesPreview, catalogMovies, navigate]
  );

  const handleResumeContinueWatching = (item: ContinueWatchingDisplayItem) => {
    const target: PlaybackTarget = {
      id: item.id,
      title: item.title,
      year: item.year,
      poster: item.poster,
      isSeries: item.isSeries,
      season: item.targetSeason ?? item.season,
      episode: item.targetEpisode ?? item.episode,
      resumeTime: item.currentTime,
      source: item.source || 'yomovies',
      isHindiDubbed: item.isHindiDubbed,
      canonicalSeriesId: item.seriesId,
      duration_s: item.duration,
    };
    triggerPlay(target);
  };

  const handleMyList = (id: number, _title: string) => {
    const allTitles = [
      ...heroItems,
      ...recentlyAddedItems,
      ...recentlyUpgradedItems,
      ...allMoviesPreview,
      ...allSeriesPreview,
      ...catalogMovies,
    ];
    const found = allTitles.find((m) => m.id === id);
    if (isInList(id)) {
      removeItem(id);
    } else if (found) {
      addItem({
        id: found.id,
        title: found.title,
        year: found.year,
        poster: found.poster || found.poster_url || null,
        is_series: Boolean(found.is_series),
        rating: found.rating,
        imdb: found.imdb,
        genres: found.genres,
        quality: found.quality,
        source: found.source,
      });
    }
  };

  return (
    <div className="home-page-container">
      {/* Featured Rotating Hero Section (Priority 0 immediate shell skeleton -> Priority 1 spotlight) */}
      {viewMode === 'discovery' && !isFilteredCategory && (
        heroItems.length > 0 ? (
          <FeaturedHero
            items={heroItems}
            onPlay={handlePlay}
            onMyList={handleMyList}
          />
        ) : sectionLoading.recentlyAdded ? (
          <section className="hero-fullbleed hero-skeleton" aria-label="Loading Featured Spotlight" aria-busy="true">
            <div className="hero-inner-container">
              <div className="hero-skeleton-lines">
                <div className="hero-skeleton-pill" />
                <div className="hero-skeleton-title" />
                <div className="hero-skeleton-desc" />
              </div>
            </div>
          </section>
        ) : null
      )}

      {/* Main Home Content Container */}
      <div className="home-content-container">
        {/* Error notification banner */}
        {error && (
          <ErrorBanner
            message={error}
            onRetry={viewMode === 'discovery' ? fetchDiscoveryData : () => fetchFilteredGrid(1, false)}
          />
        )}

        {/* VIEW MODE 1: DISCOVERY HOMEPAGE SECTIONS (each section loads independently) */}
        {viewMode === 'discovery' && !isFilteredCategory ? (
          <>
            {/* Section 1: Continue Watching (never waits for discovery APIs) */}
            <ContinueWatchingSection onResume={handleResumeContinueWatching} />

            {/* Section 2: Recently Added */}
            {preferences.recently_added_enabled && (
              <DiscoveryRow
                id="section-recently-added"
                title="Recently Added"
                icon={<Sparkles size={18} strokeWidth={2} />}
                items={recentlyAddedItems}
                loading={sectionLoading.recentlyAdded}
                error={sectionError.recentlyAdded}
                onRetry={() => void fetchRecentlyAddedSection(discoverySeqRef.current)}
                onSelectMovie={handleCardClick}
                onSeeAll={handleSeeAllRecentlyAdded}
                emptyMessage="No new titles discovered in the last 3 months."
              />
            )}

            {/* Section 3: Trending Now (Priority 2 — lazy-loaded on viewport approach, expands 18 -> 50 on right scroll) */}
            <div ref={trendingLazy.ref} data-lazy-section="trending">
              {(!sectionLoaded.trending || sectionLoading.trending || Boolean(sectionError.trending) || trendingItems.length > 0) && (
                <DiscoveryRow
                  id="section-trending-now"
                  title="Trending Now"
                  icon={<Flame size={18} strokeWidth={2} />}
                  items={trendingItems}
                  loading={!trendingLazy.isTriggered || sectionLoading.trending}
                  error={sectionError.trending}
                  onRetry={() => void fetchTrendingSection(discoverySeqRef.current)}
                  onSelectMovie={handleCardClick}
                  hasMoreHorizontal={!trendingExpanded && trendingItems.length >= INITIAL_DISCOVERY_ROW_LIMIT}
                  loadingMoreHorizontal={trendingExpanding}
                  onLoadMoreHorizontal={() => void handleExpandTrending()}
                />
              )}
            </div>

            {/* Section 4: Evergreen Picks / Recommended for You (Priority 2 — lazy-loaded, expands 18 -> 50 on right scroll) */}
            <div ref={evergreenLazy.ref} data-lazy-section="evergreen">
              {(!sectionLoaded.evergreen || sectionLoading.evergreen || Boolean(sectionError.evergreen) || recommendedItems.length > 0) && (
                <DiscoveryRow
                  id="section-recommended-for-you"
                  title={recommendedPersonalized ? 'Recommended for You' : 'Evergreen Picks'}
                  icon={<ThumbsUp size={18} strokeWidth={2} />}
                  items={recommendedItems}
                  loading={!evergreenLazy.isTriggered || sectionLoading.evergreen}
                  error={sectionError.evergreen}
                  onRetry={() => void fetchEvergreenOrRecommendedSection(discoverySeqRef.current)}
                  onSelectMovie={handleCardClick}
                  hasMoreHorizontal={!evergreenExpanded && recommendedItems.length >= INITIAL_DISCOVERY_ROW_LIMIT}
                  loadingMoreHorizontal={evergreenExpanding}
                  onLoadMoreHorizontal={() => void handleExpandEvergreen()}
                />
              )}
            </div>

            {/* Recently Upgraded (Priority 2 — lazy-loaded, only shown when verified upgrades exist) */}
            {preferences.recently_upgraded_enabled && (
              <div ref={upgradedLazy.ref} data-lazy-section="recently-upgraded">
                {recentlyUpgradedItems.length > 0 && (
                  <DiscoveryRow
                    id="section-recently-upgraded"
                    title="Recently Upgraded"
                    icon={<TrendingUp size={18} strokeWidth={2} />}
                    items={recentlyUpgradedItems}
                    loading={sectionLoading.recentlyUpgraded}
                    error={sectionError.recentlyUpgraded}
                    onRetry={() => void fetchRecentlyUpgradedSection(discoverySeqRef.current)}
                    onSelectMovie={handleCardClick}
                    onSeeAll={handleSeeAllRecentlyUpgraded}
                    isUpgradeRow={true}
                    emptyMessage="No quality upgrades recorded within the last 3 months."
                  />
                )}
              </div>
            )}

            {/* Section 4b: Browse by Year (Priority 2 — lazy-loaded on viewport approach) */}
            <div ref={yearsLazy.ref} data-lazy-section="years">
              <BrowseByYear
                years={catalogYears}
                olderCount={olderYearsCount}
                selectedYear={filters.year}
                onSelectYear={handleSelectYear}
                loading={!yearsLazy.isTriggered || sectionLoading.years}
              />
            </div>

            {/* Section 5: All Movies (Priority 2 — lazy-loaded on viewport approach) */}
            <div ref={moviesLazy.ref} data-lazy-section="movies">
              <DiscoveryRow
                id="section-all-movies"
                title="Feature Films & Movies"
                icon={<Film size={18} strokeWidth={2} />}
                items={allMoviesPreview}
                loading={!moviesLazy.isTriggered || sectionLoading.movies}
                error={sectionError.movies}
                onRetry={() => void fetchMoviesSection(discoverySeqRef.current)}
                onSelectMovie={handleCardClick}
                onSeeAll={handleSeeAllMovies}
                seeAllLabel="Explore All Movies"
              />
            </div>

            {/* Section 6: All Series (Priority 2 — lazy-loaded on viewport approach) */}
            <div ref={seriesLazy.ref} data-lazy-section="series">
              <DiscoveryRow
                id="section-all-series"
                title="Web Series & Television"
                icon={<Tv size={18} strokeWidth={2} />}
                items={allSeriesPreview}
                loading={!seriesLazy.isTriggered || sectionLoading.series}
                error={sectionError.series}
                onRetry={() => void fetchSeriesSection(discoverySeqRef.current)}
                onSelectMovie={handleCardClick}
                onSeeAll={handleSeeAllSeries}
                seeAllLabel="Explore All Series"
              />
            </div>
          </>
        ) : (
          /* VIEW MODE 2: FILTERED CATALOGUE GRID */
          <>
            <div className="catalogue-breadcrumb-bar">
              <button
                type="button"
                className="btn-breadcrumb-back"
                onClick={handleResetToDiscovery}
              >
                ← Back to Discovery
              </button>
            </div>

            {gridLoading ? (
              <LoadingSkeleton count={18} />
            ) : (
              <>
                <ContentGrid
                  title={gridTitle}
                  totalCount={totalCatalogCount}
                  movies={catalogMovies}
                  hasMore={hasMore}
                  isLoadingMore={isLoadingMore}
                  onLoadMore={handleLoadMore}
                  onSelectMovie={handleCardClick}
                  onResetFilters={handleResetToDiscovery}
                  filters={filters}
                  onChangeFilter={handleChangeFilter}
                  onClearFilters={handleClearFilters}
                  isUpgradeView={filters.sort === 'recently_upgraded'}
                  fiveColumnLayout={filters.sort === 'first_added' || filters.sort === 'newest_added'}
                />

                {paginationError && (
                  <div style={{ marginTop: '16px' }}>
                    <ErrorBanner message={paginationError} onRetry={handleLoadMore} />
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>

      {/* Internal React Streaming Player Modal */}
      {!onPlayTarget && (
        <PlayerModal
          isOpen={Boolean(internalPlayerTarget)}
          target={internalPlayerTarget}
          onClose={() => setInternalPlayerTarget(null)}
        />
      )}
    </div>
  );
};
