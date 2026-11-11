import React from 'react';
import { MovieItem } from '../../types/catalogue';
import { ContentCard } from './ContentCard';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { CatalogFilterBar, CatalogFilterState } from './CatalogFilterBar';

interface ContentGridProps {
  title: string;
  totalCount: number;
  movies: MovieItem[];
  hasMore: boolean;
  isLoadingMore: boolean;
  onLoadMore: () => void;
  onSelectMovie: (id: number, title: string) => void;
  onResetFilters: () => void;
  filters?: CatalogFilterState;
  onChangeFilter?: (key: keyof CatalogFilterState, value: string) => void;
  onClearFilters?: () => void;
  isUpgradeView?: boolean;
}

export const ContentGrid: React.FC<ContentGridProps> = ({
  title,
  totalCount,
  movies,
  hasMore,
  isLoadingMore,
  onLoadMore,
  onSelectMovie,
  onResetFilters,
  filters,
  onChangeFilter,
  onClearFilters,
  isUpgradeView = false,
}) => {
  return (
    <section className="catalogue-section" aria-label={title}>
      {/* Section Header */}
      <div className="catalogue-header">
        <div className="catalogue-title-group">
          <h2 className="catalogue-heading">{title}</h2>
          {totalCount > 0 && (
            <span className="catalogue-count-badge">
              {totalCount.toLocaleString()} {totalCount === 1 ? 'title' : 'titles'}
            </span>
          )}
        </div>
      </div>

      {/* Filter Bar (if filter handlers supplied) */}
      {filters && onChangeFilter && onClearFilters && (
        <CatalogFilterBar
          filters={filters}
          onChangeFilter={onChangeFilter}
          onClearFilters={onClearFilters}
          totalCount={totalCount}
        />
      )}

      {movies.length === 0 ? (
        <div className="empty-state">
          <svg className="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
            <path d="M8 11h6" />
          </svg>
          <h3 className="empty-state-title">No titles found in this category</h3>
          <p className="empty-state-desc">
            We couldn't find any matching movies or series with the selected filters.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onResetFilters}
            style={{ marginTop: '12px' }}
          >
            Reset Filters & View All
          </button>
        </div>
      ) : (
        <>
          {/* Multi-Row Responsive Grid */}
          <div className="content-grid">
            {movies.map((movie) => (
              <ContentCard
                key={movie.id}
                movie={movie}
                onSelect={onSelectMovie}
                upgradeBadge={isUpgradeView ? (movie.latest_quality_transition || movie.upgradeBadge || 'HD UPGRADE') : undefined}
              />
            ))}
          </div>

          {/* Pagination / Load More Controls */}
          <div className="pagination-wrap">
            {hasMore ? (
              <button
                type="button"
                className="btn-load-more"
                onClick={onLoadMore}
                disabled={isLoadingMore}
                aria-label="Load more movies and series"
              >
                {isLoadingMore ? (
                  <>
                    <LoadingSpinner size="sm" />
                    <span>Loading more titles...</span>
                  </>
                ) : (
                  <>
                    <span>Load More Content</span>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M6 9l6 6 6-6" />
                    </svg>
                  </>
                )}
              </button>
            ) : totalCount > 0 ? (
              <div className="end-of-catalogue-notice">
                <span className="end-dot" />
                <span>You have viewed all {totalCount.toLocaleString()} available titles</span>
                <span className="end-dot" />
              </div>
            ) : null}
          </div>
        </>
      )}
    </section>
  );
};
