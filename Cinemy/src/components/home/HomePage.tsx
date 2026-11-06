import React, { useState, useEffect, useCallback, useRef } from 'react';
import { CategorySelection } from '../layout/CategoryBar';
import { MovieItem } from '../../types/catalogue';
import { getMovies } from '../../api/catalogue';
import { FeaturedHero } from './FeaturedHero';
import { ContinueWatchingSection, ContinueWatchingDisplayItem } from '../../features/continue-watching';
import { ContentGrid } from './ContentGrid';
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
  onPlayTarget,
}) => {
  const { navigate } = useRouter();
  const { isInList, addItem, removeItem } = useWatchlist();

  const [movies, setMovies] = useState<MovieItem[]>([]);
  const [heroItems, setHeroItems] = useState<MovieItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [hasMore, setHasMore] = useState<boolean>(false);
  const [initialLoading, setInitialLoading] = useState<boolean>(true);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [paginationError, setPaginationError] = useState<string | null>(null);

  // Local fallback player target state
  const [internalPlayerTarget, setInternalPlayerTarget] = useState<PlaybackTarget | null>(null);

  const isLoadingMoreRef = useRef(false);

  // Compute clean section title based on active filters
  const getSectionTitle = (): string => {
    if (activeCategory.genre) {
      return `${activeCategory.genre} Collection`;
    }
    switch (activeCategory.category) {
      case 'movies':
        return 'Feature Films & Cinema';
      case 'series':
        return 'Trending Web Series & Shows';
      case 'punjabi':
        return 'Punjabi Cinema & Hits';
      case 'hindi-dubbed':
        return 'Hindi Dubbed & Dual Audio';
      case 'hollywood':
        return 'Hollywood English Releases';
      case 'animation':
        return 'Animation & Anime Collection';
      case 'all':
      default:
        return 'Latest Movies & Series';
    }
  };

  // Initial catalogue fetch for active category
  const fetchCatalogue = useCallback(async () => {
    setInitialLoading(true);
    setError(null);
    setPaginationError(null);
    setCurrentPage(1);

    try {
      const res = await getMovies({
        page: 1,
        per_page: 36,
        series: activeCategory.series,
        genre: activeCategory.genre,
        sort: 'recent',
      });

      const items = res.items || [];
      setMovies(items);
      setTotalCount(res.total || 0);
      setHasMore(res.has_more);

      // Select top 6 high-quality titles with valid posters for the rotating hero spotlight
      const eligibleHero = items
        .filter((item) => item.poster && !item.poster.includes('logo.png'))
        .slice(0, 6);
      setHeroItems(eligibleHero.length > 0 ? eligibleHero : items.slice(0, 6));
    } catch (err: any) {
      setError(err.message || 'Unable to load catalogue records from server.');
    } finally {
      setInitialLoading(false);
    }
  }, [activeCategory]);

  useEffect(() => {
    fetchCatalogue();
  }, [fetchCatalogue]);

  // Load More pagination
  const handleLoadMore = async () => {
    if (isLoadingMoreRef.current || !hasMore) return;
    isLoadingMoreRef.current = true;
    setIsLoadingMore(true);
    setPaginationError(null);

    const nextPage = currentPage + 1;

    try {
      const res = await getMovies({
        page: nextPage,
        per_page: 36,
        series: activeCategory.series,
        genre: activeCategory.genre,
        sort: 'recent',
      });

      const newItems = res.items || [];

      // Strict de-duplication by movie ID
      setMovies((prev) => {
        const existingIds = new Set(prev.map((m) => m.id));
        const uniqueItems = newItems.filter((m) => !existingIds.has(m.id));
        return [...prev, ...uniqueItems];
      });

      setCurrentPage(nextPage);
      setHasMore(res.has_more);
    } catch (err: any) {
      setPaginationError(err.message || 'Failed to load additional titles. Please try again.');
    } finally {
      setIsLoadingMore(false);
      isLoadingMoreRef.current = false;
    }
  };

  const triggerPlay = (target: PlaybackTarget) => {
    if (onPlayTarget) {
      onPlayTarget(target);
    } else {
      setInternalPlayerTarget(target);
    }
  };

  const handlePlay = (id: number, title: string) => {
    const found = movies.find((m) => m.id === id) || heroItems.find((m) => m.id === id);
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
      const found = movies.find((m) => m.id === id) || heroItems.find((m) => m.id === id);
      if (found?.is_series) {
        navigate(`/series/${id}`);
      } else {
        navigate(`/movie/${id}`);
      }
    },
    [movies, heroItems, navigate]
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
    const found = movies.find((m) => m.id === id) || heroItems.find((m) => m.id === id);
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
      {/* Featured Rotating Hero Section (Full-bleed 100vw stage) */}
      {!initialLoading && heroItems.length > 0 && (
        <FeaturedHero
          items={heroItems}
          onPlay={handlePlay}
          onMyList={handleMyList}
        />
      )}

      {/* Main Home Content Container — Aligned with Hero Container Margins & Safe Edge Padding */}
      <div className="home-content-container">
        {/* Continue Watching Section */}
        <ContinueWatchingSection onResume={handleResumeContinueWatching} />

        {/* Error state */}
        {error && (
          <ErrorBanner
            message={error}
            onRetry={fetchCatalogue}
          />
        )}

        {/* Loading Skeleton */}
        {initialLoading ? (
          <LoadingSkeleton count={18} />
        ) : (
          <>
            {/* Main Content Grid */}
            <ContentGrid
              title={getSectionTitle()}
              totalCount={totalCount}
              movies={movies}
              hasMore={hasMore}
              isLoadingMore={isLoadingMore}
              onLoadMore={handleLoadMore}
              onSelectMovie={handleCardClick}
              onResetFilters={onResetCategory}
            />

            {/* Non-destructive Pagination Error Banner */}
            {paginationError && (
              <div style={{ marginTop: '16px' }}>
                <ErrorBanner
                  message={paginationError}
                  onRetry={handleLoadMore}
                />
              </div>
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
