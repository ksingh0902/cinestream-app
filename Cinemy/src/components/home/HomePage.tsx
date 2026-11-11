import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Sparkles, TrendingUp, Film, Tv } from 'lucide-react';
import { CategorySelection } from '../layout/CategoryBar';
import { HomepagePreferences, MovieItem, YearCountItem } from '../../types/catalogue';
import {
  getMovies,
  getRecentlyAdded,
  getRecentlyUpgraded,
  getCatalogYears,
  getHomepagePreferences,
} from '../../api/catalogue';
import { FeaturedHero } from './FeaturedHero';
import { ContinueWatchingSection, ContinueWatchingDisplayItem } from '../../features/continue-watching';
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
  const [catalogYears, setCatalogYears] = useState<YearCountItem[]>([]);
  const [olderYearsCount, setOlderYearsCount] = useState<number>(0);
  const [allMoviesPreview, setAllMoviesPreview] = useState<MovieItem[]>([]);
  const [allSeriesPreview, setAllSeriesPreview] = useState<MovieItem[]>([]);
  const [heroItems, setHeroItems] = useState<MovieItem[]>([]);

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

  // Loading and error states
  const [initialLoading, setInitialLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [paginationError, setPaginationError] = useState<string | null>(null);

  // Local fallback player target state
  const [internalPlayerTarget, setInternalPlayerTarget] = useState<PlaybackTarget | null>(null);
  const isLoadingMoreRef = useRef(false);

  // Determine if activeCategory requires grid view
  const isFilteredCategory = Boolean(
    activeCategory.category !== 'all' || activeCategory.genre
  );

  // Fetch preferences once
  useEffect(() => {
    getHomepagePreferences()
      .then((p) => {
        if (p) setPreferences(p);
      })
      .catch(() => {});
  }, []);

  // Fetch discovery homepage rows
  const fetchDiscoveryData = useCallback(async () => {
    setInitialLoading(true);
    setError(null);
    try {
      const [addedRes, upgradedRes, yearsRes, moviesRes, seriesRes] = await Promise.all([
        getRecentlyAdded({ limit: 30, window_months: preferences.recently_added_window_months }).catch(() => ({ items: [], total: 0, window_months: 3 })),
        getRecentlyUpgraded({ limit: 30, window_months: preferences.recently_upgraded_window_months }).catch(() => ({ items: [], total: 0, window_months: 3 })),
        getCatalogYears().catch(() => ({ years: [], older_count: 0 })),
        getMovies({ per_page: 80, series: 0, sort: 'recent' }).catch(() => ({ items: [], total: 0, page: 1, per_page: 80, has_more: false })),
        getMovies({ per_page: 80, series: 1, sort: 'recent' }).catch(() => ({ items: [], total: 0, page: 1, per_page: 80, has_more: false })),
      ]);

      const recentAddedList = addedRes.items || [];
      const addedIds = new Set(recentAddedList.map((m) => m.id));
      const addedTitles = new Set(recentAddedList.map((m) => (m.title || '').toLowerCase().replace(/\s*[\[(]\s*(?:19|20)\d{2}\s*[\])]/g, '').trim()));

      // Exclude titles already showcased in Recently Added to avoid duplicate cards on homepage
      const moviesPreview = (moviesRes.items || [])
        .filter((m) => !addedIds.has(m.id) && !addedTitles.has((m.title || '').toLowerCase().replace(/\s*[\[(]\s*(?:19|20)\d{2}\s*[\])]/g, '').trim()))
        .slice(0, 30);

      const seriesPreview = (seriesRes.items || [])
        .filter((m) => !addedIds.has(m.id) && !addedTitles.has((m.title || '').toLowerCase().replace(/\s*[\[(]\s*(?:19|20)\d{2}\s*[\])]/g, '').trim()))
        .slice(0, 30);

      setRecentlyAddedItems(recentAddedList);
      setRecentlyUpgradedItems(upgradedRes.items || []);
      setCatalogYears(yearsRes.years || []);
      setOlderYearsCount(yearsRes.older_count || 0);
      setAllMoviesPreview(moviesPreview);
      setAllSeriesPreview(seriesPreview);

      // Rotate high-quality posters for spotlight hero
      const candidateHero = [
        ...(addedRes.items || []),
        ...(moviesRes.items || []),
      ].filter((m) => m.poster && !m.poster.includes('logo.png'));

      const uniqueHero = Array.from(new Map(candidateHero.map((m) => [m.id, m])).values());
      setHeroItems(uniqueHero.slice(0, 6));
    } catch (err: any) {
      setError(err.message || 'Unable to load discovery catalogue.');
    } finally {
      setInitialLoading(false);
    }
  }, [preferences.recently_added_window_months, preferences.recently_upgraded_window_months]);

  // Fetch filtered catalogue grid
  const fetchFilteredGrid = useCallback(
    async (pageToFetch: number = 1, append: boolean = false) => {
      if (pageToFetch === 1) {
        setInitialLoading(true);
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
        setInitialLoading(false);
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
    [heroItems, recentlyAddedItems, recentlyUpgradedItems, allMoviesPreview, allSeriesPreview, catalogMovies, navigate]
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
      {!initialLoading && heroItems.length > 0 && viewMode === 'discovery' && (
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

        {/* VIEW MODE 1: DISCOVERY HOMEPAGE SECTIONS */}
        {viewMode === 'discovery' && !isFilteredCategory ? (
          <>
            {/* Section 1: Continue Watching */}
            <ContinueWatchingSection onResume={handleResumeContinueWatching} />

            {initialLoading ? (
              <div style={{ marginTop: '24px' }}>
                <LoadingSkeleton count={12} />
              </div>
            ) : (
              <>
                {/* Section 2: Recently Added */}
                {preferences.recently_added_enabled && (
                  <DiscoveryRow
                    id="section-recently-added"
                    title="Recently Added"
                    icon={<Sparkles size={18} strokeWidth={2} />}
                    count={recentlyAddedItems.length}
                    items={recentlyAddedItems}
                    onSelectMovie={handleCardClick}
                    onSeeAll={handleSeeAllRecentlyAdded}
                    emptyMessage="No new titles discovered in the last 3 months."
                  />
                )}

                {/* Section 3: Recently Upgraded (only shown when verified upgrades exist) */}
                {preferences.recently_upgraded_enabled && recentlyUpgradedItems.length > 0 && (
                  <DiscoveryRow
                    id="section-recently-upgraded"
                    title="Recently Upgraded"
                    icon={<TrendingUp size={18} strokeWidth={2} />}
                    count={recentlyUpgradedItems.length}
                    items={recentlyUpgradedItems}
                    onSelectMovie={handleCardClick}
                    onSeeAll={handleSeeAllRecentlyUpgraded}
                    isUpgradeRow={true}
                    emptyMessage="No quality upgrades recorded within the last 3 months."
                  />
                )}

                {/* Section 4: Browse by Year */}
                <BrowseByYear
                  years={catalogYears}
                  olderCount={olderYearsCount}
                  selectedYear={filters.year}
                  onSelectYear={handleSelectYear}
                  loading={initialLoading}
                />

                {/* Section 5: All Movies */}
                <DiscoveryRow
                  id="section-all-movies"
                  title="Feature Films & Movies"
                  icon={<Film size={18} strokeWidth={2} />}
                  count={allMoviesPreview.length}
                  items={allMoviesPreview}
                  onSelectMovie={handleCardClick}
                  onSeeAll={handleSeeAllMovies}
                  seeAllLabel="Explore All Movies"
                />

                {/* Section 6: All Series */}
                <DiscoveryRow
                  id="section-all-series"
                  title="Web Series & Television"
                  icon={<Tv size={18} strokeWidth={2} />}
                  count={allSeriesPreview.length}
                  items={allSeriesPreview}
                  onSelectMovie={handleCardClick}
                  onSeeAll={handleSeeAllSeries}
                  seeAllLabel="Explore All Series"
                />
              </>
            )}
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

            {initialLoading ? (
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
