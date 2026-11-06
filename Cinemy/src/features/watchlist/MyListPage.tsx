import React, { useState, useMemo } from 'react';
import { HardDrive, Bookmark, X } from 'lucide-react';
import { useWatchlist } from './useWatchlist';
import { useRouter } from '../../router';
import { getPosterUrl, formatRating } from '../../utils/formatters';

export const MyListPage: React.FC = () => {
  const { items, removeItem } = useWatchlist();
  const { navigate } = useRouter();
  const [filter, setFilter] = useState<'all' | 'movies' | 'series'>('all');

  const filteredItems = useMemo(() => {
    if (filter === 'movies') return items.filter((it) => !it.is_series);
    if (filter === 'series') return items.filter((it) => it.is_series);
    return items;
  }, [items, filter]);

  const handleCardClick = (id: number, isSeries: boolean) => {
    navigate(isSeries ? `/series/${id}` : `/movie/${id}`);
  };

  return (
    <div className="watchlist-page-container">
      <div className="page-header-row">
        <div>
          <h1 className="page-title">My List</h1>
          <p className="page-subtitle">
            Saved movies and series for quick access ({items.length} titles)
          </p>
        </div>

        {/* Filter Pills */}
        <div className="filter-pill-group">
          <button
            type="button"
            className={`filter-pill ${filter === 'all' ? 'active' : ''}`}
            onClick={() => setFilter('all')}
          >
            All ({items.length})
          </button>
          <button
            type="button"
            className={`filter-pill ${filter === 'movies' ? 'active' : ''}`}
            onClick={() => setFilter('movies')}
          >
            Movies ({items.filter((it) => !it.is_series).length})
          </button>
          <button
            type="button"
            className={`filter-pill ${filter === 'series' ? 'active' : ''}`}
            onClick={() => setFilter('series')}
          >
            Series ({items.filter((it) => it.is_series).length})
          </button>
        </div>
      </div>

      <div className="storage-disclosure-banner">
        <span className="disclosure-icon"><HardDrive size={15} strokeWidth={1.5} /></span>
        <span>
          <strong>Device-local storage:</strong> My List items are safely stored on this device.
        </span>
      </div>

      {filteredItems.length === 0 ? (
        <div className="watchlist-empty-state">
          <div className="empty-icon"><Bookmark size={40} strokeWidth={1.5} /></div>
          <h3 className="empty-title">
            {items.length === 0 ? 'Your list is empty' : `No ${filter} found in your list`}
          </h3>
          <p className="empty-desc">
            {items.length === 0
              ? 'Add movies and series to your list from the catalogue to watch them later.'
              : 'Try changing your filter or add more titles from the catalogue.'}
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => navigate('/')}
          >
            Browse Catalogue
          </button>
        </div>
      ) : (
        <div className="watchlist-grid">
          {filteredItems.map((item) => {
            const ratingBadge = formatRating(item.rating, item.imdb);
            return (
              <div
                key={item.id}
                className="watchlist-card"
                role="button"
                tabIndex={0}
                onClick={() => handleCardClick(item.id, item.is_series)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleCardClick(item.id, item.is_series);
                  }
                }}
                aria-label={`${item.title} (${item.year || 'Unknown'}), ${item.is_series ? 'Series' : 'Movie'}`}
              >
                <div className="watchlist-card-poster-wrap">
                  <img
                    src={getPosterUrl(item.poster, item.title, item.year)}
                    alt={item.title}
                    className="watchlist-card-img"
                    loading="lazy"
                  />
                  <div className="card-badge-top-left">
                    {item.is_series ? (
                      <span className="badge-tag series">Series</span>
                    ) : (
                      <span className="badge-tag movie">Movie</span>
                    )}
                  </div>
                  {ratingBadge && (
                    <div className="card-badge-top-right">
                      <span className="badge-tag rating">{ratingBadge}</span>
                    </div>
                  )}

                  {/* Remove Button overlay */}
                  <button
                    type="button"
                    className="btn-remove-watchlist"
                    title="Remove from My List"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeItem(item.id);
                    }}
                    aria-label={`Remove ${item.title} from My List`}
                  >
                    <X size={14} strokeWidth={1.5} />
                  </button>
                </div>

                <div className="watchlist-card-body">
                  <h4 className="watchlist-card-title" title={item.title}>
                    {item.title}
                  </h4>
                  <div className="watchlist-card-meta">
                    <span>{item.year || '—'}</span>
                    {item.genres && item.genres[0] && <span>{item.genres[0]}</span>}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

