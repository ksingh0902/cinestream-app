import React, { useState, useEffect, useCallback, useRef } from 'react';
import { AlertTriangle, ArrowLeft } from 'lucide-react';
import { MovieItem } from '../../types/catalogue';
import { getMovies } from '../../api/catalogue';
import { useRouter } from '../../router';
import { getPosterUrl, formatRating } from '../../utils/formatters';
import { LoadingSpinner } from '../../components/common/LoadingSpinner';

interface GenrePageProps {
  genreName: string;
}

export const GenrePage: React.FC<GenrePageProps> = ({ genreName }) => {
  const { navigate, back } = useRouter();

  const [movies, setMovies] = useState<MovieItem[]>([]);
  const [filterType, setFilterType] = useState<'all' | 'movies' | 'series'>('all');
  const [totalCount, setTotalCount] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [hasMore, setHasMore] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [loadingMore, setLoadingMore] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const isLoadingMoreRef = useRef(false);

  const decodedGenre = decodeURIComponent(genreName);

  const fetchGenreMovies = useCallback(async () => {
    setLoading(true);
    setError(null);
    setCurrentPage(1);

    const seriesParam =
      filterType === 'movies' ? 0 : filterType === 'series' ? 1 : undefined;

    try {
      const res = await getMovies({
        genre: decodedGenre,
        series: seriesParam,
        page: 1,
        per_page: 36,
        sort: 'recent',
      });

      setMovies(res.items || []);
      setTotalCount(res.total || 0);
      setHasMore(res.has_more);
    } catch (err: any) {
      console.error('Genre fetch error:', err);
      setError(err.message || 'Failed to load genre collection.');
    } finally {
      setLoading(false);
    }
  }, [decodedGenre, filterType]);

  useEffect(() => {
    fetchGenreMovies();
  }, [fetchGenreMovies]);

  const handleLoadMore = async () => {
    if (isLoadingMoreRef.current || !hasMore) return;
    isLoadingMoreRef.current = true;
    setLoadingMore(true);

    const nextPage = currentPage + 1;
    const seriesParam =
      filterType === 'movies' ? 0 : filterType === 'series' ? 1 : undefined;

    try {
      const res = await getMovies({
        genre: decodedGenre,
        series: seriesParam,
        page: nextPage,
        per_page: 36,
        sort: 'recent',
      });

      const newItems = res.items || [];
      setMovies((prev) => {
        const existingIds = new Set(prev.map((m) => m.id));
        const uniqueItems = newItems.filter((m) => !existingIds.has(m.id));
        return [...prev, ...uniqueItems];
      });

      setCurrentPage(nextPage);
      setHasMore(res.has_more);
    } catch (err: any) {
      console.error('Load more error:', err);
    } finally {
      setLoadingMore(false);
      isLoadingMoreRef.current = false;
    }
  };

  const handleCardClick = (item: MovieItem) => {
    navigate(item.is_series ? `/series/${item.id}` : `/movie/${item.id}`);
  };

  return (
    <div className="genre-page-container">
      {/* Header Row */}
      <div className="page-header-row">
        <div>
          <button type="button" className="btn-nav-back" onClick={back} style={{ marginBottom: '8px' }}>
            <ArrowLeft size={16} strokeWidth={1.5} /><span>Back</span>
          </button>
          <h1 className="page-title">{decodedGenre} Collection</h1>
          <p className="page-subtitle">
            Browsing {totalCount} titles under &ldquo;{decodedGenre}&rdquo;
          </p>
        </div>

        {/* Filter Pills */}
        <div className="filter-pill-group">
          <button
            type="button"
            className={`filter-pill ${filterType === 'all' ? 'active' : ''}`}
            onClick={() => setFilterType('all')}
          >
            All
          </button>
          <button
            type="button"
            className={`filter-pill ${filterType === 'movies' ? 'active' : ''}`}
            onClick={() => setFilterType('movies')}
          >
            Movies
          </button>
          <button
            type="button"
            className={`filter-pill ${filterType === 'series' ? 'active' : ''}`}
            onClick={() => setFilterType('series')}
          >
            Series
          </button>
        </div>
      </div>

      {loading ? (
        <div className="genre-loading-box">
          <LoadingSpinner label={`Loading ${decodedGenre} titles...`} size="lg" />
        </div>
      ) : error ? (
        <div className="genre-error-box">
          <p className="error-text"><AlertTriangle size={16} strokeWidth={1.5} style={{ verticalAlign: "middle", marginRight: 6 }} /> {error}</p>
          <button type="button" className="btn btn-primary" onClick={fetchGenreMovies}>
            Retry
          </button>
        </div>
      ) : movies.length === 0 ? (
        <div className="genre-empty-box">
          <h3>No titles found for &ldquo;{decodedGenre}&rdquo;</h3>
          <p>Try selecting another genre from the catalogue.</p>
          <button type="button" className="btn btn-secondary" onClick={() => navigate('/')}>
            Explore All Titles
          </button>
        </div>
      ) : (
        <>
          <div className="genre-grid">
            {movies.map((item) => {
              const ratingBadge = formatRating(item.rating, item.imdb);
              const isSeries = Boolean(item.is_series);
              return (
                <div
                  key={item.id}
                  className="content-card"
                  role="button"
                  tabIndex={0}
                  onClick={() => handleCardClick(item)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleCardClick(item);
                    }
                  }}
                  aria-label={`${item.title} (${item.year || 'Unknown'}), ${isSeries ? 'Series' : 'Movie'}`}
                >
                  <div className="card-poster-wrap">
                    <img
                      className="card-poster-img"
                      src={getPosterUrl(item.poster || item.poster_url, item.title, item.year)}
                      alt={item.title}
                      loading="lazy"
                    />
                    <div className="card-badge-top-left">
                      <span className={`badge-tag ${isSeries ? 'series' : 'movie'}`}>
                        {isSeries ? 'Series' : 'Movie'}
                      </span>
                    </div>
                    {ratingBadge && (
                      <div className="card-badge-top-right">
                        <span className="badge-tag rating">{ratingBadge}</span>
                      </div>
                    )}
                  </div>
                  <div className="card-body">
                    <h4 className="card-title" title={item.title}>
                      {item.title}
                    </h4>
                    <div className="card-footer">
                      <span>{item.year || '—'}</span>
                      {item.quality && <span>{item.quality}</span>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {hasMore && (
            <div className="load-more-container" style={{ textAlign: 'center', marginTop: '32px' }}>
              <button
                type="button"
                className="btn btn-secondary btn-load-more"
                onClick={handleLoadMore}
                disabled={loadingMore}
              >
                {loadingMore ? 'Loading More Titles...' : 'Load More Titles'}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};

