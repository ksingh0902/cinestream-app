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
  const [recommendedItems, setRecommendedItems] = useState<MovieItem[]>([]);
  const [recommendedPersonalized, setRecommendedPersonalized] = useState<boolean>(false);
  const [catalogYears, setCatalogYears] = useState<YearCountItem[]>([]);
  const [olderYearsCount, setOlderYearsCount] = useState<number>(0);
  const [allMoviesPreview, setAllMoviesPreview] = useState<MovieItem[]>([]);
  const [allSeriesPreview, setAllSeriesPreview] = useState<MovieItem[]>([]);
  const [heroItems, setHeroItems] = useState<MovieItem[]>([]);

  // Independent per-section loading & error states (no all-or-nothing Promise.all gate)
  type SectionKey = 'recentlyAdded' | 'trending' | 'evergreen' | 'recentlyUpgraded' | 'movies' | 'series' | 'years';
  const [sectionLoading, setSectionLoading] = useState<Record<SectionKey, boolean>>({
    recentlyAdded: true,
    trending: true,
    evergreen: true,
    recentlyUpgraded: true,
    movies: true,
    series: true,
    years: true,
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

  // Filtered catalogue grid state (for category tabs, search, filters, or See All)
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
  const discoverySeqRef = useRef(0);
  const recentAddedRef = useRef<MovieItem[]>([]);
  const rawMoviesRef = useRef<MovieItem[]>([]);
  const rawSeriesRef = useRef<MovieItem[]>([]);

  // Determine if activeCategory requires grid view
  const isFilteredCategory = Boolean(
    activeCategory.category !== 'all' || activeCategory.genre
  );

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
        .slice(0, 30);
      setAllMoviesPreview(moviesPreview);
    }

    if (rawSeriesRef.current.length > 0) {
      const seriesPreview = rawSeriesRef.current
        .filter((m) => !addedIds.has(m.id) && !addedTitles.has((m.title || '').toLowerCase().replace(/\s*[\[(]\s*(?:19|20)\d{2}\s*[\])]/g, '').trim()))
        .slice(0, 30);
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
          limit: 30,
          window_months: preferences.recently_added_window_months,
          latest_crawl: true,
        });
        if (discoverySeqRef.current !== seq) return;
        const items = addedRes.items || [];
        recentAddedRef.current = items;
        setRecentlyAddedItems(items);
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
    try {
      const trendingRes = await getTrending({ limit: 50 });
      if (discoverySeqRef.current !== seq) return;
      setTrendingItems(trendingRes.items || []);
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

  // Option A: Server-side-only personalization eligibility. Never send device-local seed_ids.
  // If /api/discovery/recommended fails or returns empty, explicitly fall back to /api/discovery/evergreen?limit=50.
  const fetchEvergreenOrRecommendedSection = useCallback(async (seq: number) => {
    setSectionLoading((prev) => ({ ...prev, evergreen: true }));
    setSectionError((prev) => ({ ...prev, evergreen: null }));
    try {
      const recRes = await getRecommended({ limit: 50 });
      if (discoverySeqRef.current !== seq) return;
      if (recRes && Array.isArray(recRes.items) && recRes.items.length > 0) {
        setRecommendedItems(recRes.items);
        setRecommendedPersonalized(Boolean(recRes.personalized));
        return;
      }
      // Empty response -> fall back to dedicated Evergreen endpoint
      const evRes = await getEvergreen({ limit: 50 });
      if (discoverySeqRef.current !== seq) return;
      setRecommendedItems(evRes.items || []);
      setRecommendedPersonalized(false);
    } catch {
      if (discoverySeqRef.current !== seq) return;
      try {
        const evRes = await getEvergreen({ limit: 50 });
        if (discoverySeqRef.current !== seq) return;
        setRecommendedItems(evRes.items || []);
        setRecommendedPersonalized(false);
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

  const fetchRecentlyUpgradedSection = useCallback(
    async (seq: number) => {
      setSectionLoading((prev) => ({ ...prev, recentlyUpgraded: true }));
      setSectionError((prev) => ({ ...prev, recentlyUpgraded: null }));
      try {
        const upgradedRes = await getRecentlyUpgraded({
          limit: 30,
          window_months: preferences.recently_upgraded_window_months,
        });
        if (discoverySeqRef.current !== seq) return;
        setRecentlyUpgradedItems(upgradedRes.items || []);
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
        const moviesRes = await getMovies({ per_page: 80, series: 0, sort: 'recent' });
        if (discoverySeqRef.current !== seq) return;
        rawMoviesRef.current = moviesRes.items || [];
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
        const seriesRes = await getMovies({ per_page: 80, series: 1, sort: 'recent' });
        if (discoverySeqRef.current !== seq) return;
        rawSeriesRef.current = seriesRes.items || [];
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
    } catch {
      if (discoverySeqRef.current !== seq) return;
      setSectionError((prev) => ({ ...prev, years: 'Unable to load release years.' }));
    } finally {
      if (discoverySeqRef.current === seq) {
        setSectionLoading((prev) => ({ ...prev, years: false }));
      }
    }
  }, []);

  // Launch all discovery homepage sections independently (no all-or-nothing Promise.all gate)
  const fetchDiscoveryData = useCallback(() => {
    const seq = ++discoverySeqRef.current;
    setError(null);
    void Promise.allSettled([
      fetchRecentlyAddedSection(seq),
      fetchTrendingSection(seq),
      fetchEvergreenOrRecommendedSection(seq),
      fetchRecentlyUpgradedSection(seq),
      fetchYearsSection(seq),
      fetchMoviesSection(seq),
      fetchSeriesSection(seq),
    ]);
  }, [
    fetchRecentlyAddedSection,
    fetchTrendingSection,
    fetchEvergreenOrRecommendedSection,
    fetchRecentlyUpgradedSection,
    fetchYearsSection,
    fetchMoviesSection,
    fetchSeriesSection,
  ]);

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

        const res = await getMovies({
          page: pageToFetch,
          per_page: 36,
          series: seriesParam,
          genre: effectiveGenre,
          year: filters.year,
          quality: filters.quality,
          language: filters.language,
          sort: (filters.sort as any) || preferences.default_sort || 'recent',
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
    } else {
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
      {/* Featured Rotating Hero Section (Full-bleed spotlight) */}
      {heroItems.length > 0 && viewMode === 'discovery' && (
        <FeaturedHero
          items={heroItems}
          onPlay={handlePlay}
          onMyList={handleMyList}
        />
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

            {/* Section 3: Trending Now */}
            {(sectionLoading.trending || Boolean(sectionError.trending) || trendingItems.length > 0) && (
              <DiscoveryRow
                id="section-trending-now"
                title="Trending Now"
                icon={<Flame size={18} strokeWidth={2} />}
                items={trendingItems}
                loading={sectionLoading.trending}
                error={sectionError.trending}
                onRetry={() => void fetchTrendingSection(discoverySeqRef.current)}
                onSelectMovie={handleCardClick}
              />
            )}

            {/* Section 4: Evergreen Picks (or Recommended for You when server-side activity qualifies) */}
            {(sectionLoading.evergreen || Boolean(sectionError.evergreen) || recommendedItems.length > 0) && (
              <DiscoveryRow
                id="section-recommended-for-you"
                title={recommendedPersonalized ? 'Recommended for You' : 'Evergreen Picks'}
                icon={<ThumbsUp size={18} strokeWidth={2} />}
                items={recommendedItems}
                loading={sectionLoading.evergreen}
                error={sectionError.evergreen}
                onRetry={() => void fetchEvergreenOrRecommendedSection(discoverySeqRef.current)}
                onSelectMovie={handleCardClick}
              />
            )}

            {/* Recently Upgraded (only shown when verified upgrades exist) */}
            {preferences.recently_upgraded_enabled && recentlyUpgradedItems.length > 0 && (
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

            {/* Section 4b: Browse by Year */}
            <BrowseByYear
              years={catalogYears}
              olderCount={olderYearsCount}
              selectedYear={filters.year}
              onSelectYear={handleSelectYear}
              loading={sectionLoading.years}
            />

            {/* Section 5: All Movies */}
            <DiscoveryRow
              id="section-all-movies"
              title="Feature Films & Movies"
              icon={<Film size={18} strokeWidth={2} />}
              items={allMoviesPreview}
              loading={sectionLoading.movies}
              error={sectionError.movies}
              onRetry={() => void fetchMoviesSection(discoverySeqRef.current)}
              onSelectMovie={handleCardClick}
              onSeeAll={handleSeeAllMovies}
              seeAllLabel="Explore All Movies"
            />

            {/* Section 6: All Series */}
            <DiscoveryRow
              id="section-all-series"
              title="Web Series & Television"
              icon={<Tv size={18} strokeWidth={2} />}
              items={allSeriesPreview}
              loading={sectionLoading.series}
              error={sectionError.series}
              onRetry={() => void fetchSeriesSection(discoverySeqRef.current)}
              onSelectMovie={handleCardClick}
              onSeeAll={handleSeeAllSeries}
              seeAllLabel="Explore All Series"
            />
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
