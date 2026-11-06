import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Search, X, AlertTriangle } from 'lucide-react';
import { MovieItem } from '../../types/catalogue';
import { getMovies } from '../../api/catalogue';
import { useRouter } from '../../router';
import { useDebounce } from '../../hooks/useDebounce';
import { getPosterUrl, formatRating } from '../../utils/formatters';
import { LoadingSpinner } from '../../components/common/LoadingSpinner';

export const SearchPage: React.FC = () => {
  const { navigate, search: urlSearch } = useRouter();

  // Read initial query from ?q= if present
  const initialQuery = useMemo(() => {
    if (typeof window === 'undefined') return '';
    const params = new URLSearchParams(urlSearch);
    return params.get('q') || '';
  }, [urlSearch]);

  const [query, setQuery] = useState<string>(initialQuery);
  const [filterType, setFilterType] = useState<'all' | 'movies' | 'series'>('all');
  const [results, setResults] = useState<MovieItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const debouncedQuery = useDebounce(query, 300);
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus search input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Fetch full catalogue results on debounced query
  useEffect(() => {
    const trimmed = debouncedQuery.trim();
    if (!trimmed) {
      setResults([]);
      setLoading(false);
      setError(null);
      return;
    }

    let isCurrent = true;
    setLoading(true);
    setError(null);

    const seriesParam =
      filterType === 'movies' ? 0 : filterType === 'series' ? 1 : undefined;

    getMovies({
      q: trimmed,
      series: seriesParam,
      per_page: 36,
      sort: 'recent',
    })
      .then((res) => {
        if (!isCurrent) return;
        setResults(res.items || []);
      })
      .catch((err: any) => {
        if (!isCurrent) return;
        console.error('Search error:', err);
        setError(err.message || 'Search service is temporarily unavailable.');
      })
      .finally(() => {
        if (isCurrent) setLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [debouncedQuery, filterType]);

  const handleCardClick = (item: MovieItem) => {
    navigate(item.is_series ? `/series/${item.id}` : `/movie/${item.id}`);
  };

  const handleClear = () => {
    setQuery('');
    setResults([]);
    inputRef.current?.focus();
  };

  const popularTags = [
    'Action',
    'Comedy',
    'Drama',
    'Thriller',
    'Horror',
    'Punjabi',
    'Hindi Dubbed',
    'Romance',
    'Crime',
    'Sci-Fi',
  ];

  return (
    <div className="search-page-container">
      {/* Search Input Bar */}
      <div className="search-page-bar-wrap">
        <div className="search-input-box-large">
          <Search size={20} strokeWidth={1.5} />
          <input
            ref={inputRef}
            type="search"
            className="search-input-field-large"
            placeholder="Search by title, genre, year..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') handleClear();
            }}
            autoComplete="off"
          />
          {query && (
            <button
              type="button"
              className="btn-clear-search-large"
              onClick={handleClear}
              title="Clear search"
            >
              <X size={16} strokeWidth={1.5} />
            </button>
          )}
        </div>

        {/* Filter Pills */}
        <div className="search-filters-row">
          <button
            type="button"
            className={`filter-pill ${filterType === 'all' ? 'active' : ''}`}
            onClick={() => setFilterType('all')}
          >
            All Titles
          </button>
          <button
            type="button"
            className={`filter-pill ${filterType === 'movies' ? 'active' : ''}`}
            onClick={() => setFilterType('movies')}
          >
            Movies Only
          </button>
          <button
            type="button"
            className={`filter-pill ${filterType === 'series' ? 'active' : ''}`}
            onClick={() => setFilterType('series')}
          >
            Series Only
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      {loading ? (
        <div className="search-loading-box">
          <LoadingSpinner label={`Searching for "${debouncedQuery}"...`} size="md" />
        </div>
      ) : error ? (
        <div className="search-error-box">
          <p className="error-text"><AlertTriangle size={16} strokeWidth={1.5} style={{ verticalAlign: "middle", marginRight: 6 }} /> {error}</p>
        </div>
      ) : query.trim().length === 0 ? (
        /* Empty Query: Suggest popular tags */
        <div className="search-starter-box">
          <h3 className="starter-title">Explore by Popular Genres</h3>
          <div className="popular-tags-grid">
            {popularTags.map((tag) => (
              <button
                key={tag}
                type="button"
                className="popular-tag-btn"
                onClick={() => setQuery(tag)}
              >
                {tag}
              </button>
            ))}
          </div>
        </div>
      ) : results.length === 0 ? (
        /* No Results Found */
        <div className="search-empty-results">
          <div className="empty-icon"><Search size={40} strokeWidth={1.5} /></div>
          <h3>No titles found matching &ldquo;{debouncedQuery}&rdquo;</h3>
          <p>Check your spelling or try searching for another title or genre.</p>
        </div>
      ) : (
        /* Results Grid */
        <div className="search-results-section">
          <div className="results-count-banner">
            Found {results.length} results for &ldquo;{debouncedQuery}&rdquo;
          </div>
          <div className="search-results-grid">
            {results.map((item) => {
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
        </div>
      )}
    </div>
  );
};
