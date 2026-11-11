import React from 'react';
import { Filter, ArrowUpDown } from 'lucide-react';

export interface CatalogFilterState {
  genre?: string;
  year?: string;
  language?: string;
  quality?: string;
  sort?: string;
}

interface CatalogFilterBarProps {
  filters: CatalogFilterState;
  onChangeFilter: (key: keyof CatalogFilterState, value: string) => void;
  onClearFilters: () => void;
  genres?: string[];
  years?: string[];
  totalCount?: number;
}

const COMMON_GENRES = [
  'Action', 'Comedy', 'Drama', 'Thriller', 'Horror', 'Romance',
  'Crime', 'Mystery', 'Sci-fi', 'Animation', 'Bollywood', 'Hollywood', 'Punjabi'
];

const COMMON_LANGUAGES = ['Hindi', 'English', 'Punjabi', 'Tamil', 'Telugu'];

const COMMON_QUALITIES = ['4K', '1080p', '720p', 'HD'];

const SORT_OPTIONS = [
  { value: 'recent', label: 'Default: Recommended' },
  { value: 'first_added', label: 'Newest Added' },
  { value: 'recently_upgraded', label: 'Recently Upgraded' },
  { value: 'year', label: 'Release Year: Newest First' },
  { value: 'quality', label: 'Highest Available Quality' },
  { value: 'title', label: 'Alphabetical (A–Z)' },
  { value: 'rating', label: 'IMDb / Top Rating' },
];

export const CatalogFilterBar: React.FC<CatalogFilterBarProps> = ({
  filters,
  onChangeFilter,
  onClearFilters,
  genres = COMMON_GENRES,
  years = ['2026', '2025', '2024', '2023', '2022', '2021', '2020', 'older'],
  totalCount,
}) => {
  const hasActiveFilters = Boolean(
    filters.genre || filters.year || filters.language || filters.quality || (filters.sort && filters.sort !== 'recent')
  );

  return (
    <div className="catalog-filter-bar" role="search" aria-label="Catalogue filters">
      <div className="filter-controls-group">
        <div className="filter-label-group">
          <Filter size={15} strokeWidth={2} />
          <span>Filters</span>
        </div>

        {/* Genre Filter */}
        <div className="filter-select-wrap">
          <label htmlFor="filter-genre" className="sr-only">Filter by Genre</label>
          <select
            id="filter-genre"
            className="filter-select"
            value={filters.genre || ''}
            onChange={(e) => onChangeFilter('genre', e.target.value)}
          >
            <option value="">All Genres</option>
            {genres.map((g) => (
              <option key={`g-${g}`} value={g}>{g}</option>
            ))}
          </select>
        </div>

        {/* Release Year Filter */}
        <div className="filter-select-wrap">
          <label htmlFor="filter-year" className="sr-only">Filter by Year</label>
          <select
            id="filter-year"
            className="filter-select"
            value={filters.year || ''}
            onChange={(e) => onChangeFilter('year', e.target.value)}
          >
            <option value="">All Years</option>
            {years.map((y) => (
              <option key={`y-${y}`} value={y}>{y === 'older' ? 'Older (Pre-2020)' : y}</option>
            ))}
          </select>
        </div>

        {/* Language Filter */}
        <div className="filter-select-wrap">
          <label htmlFor="filter-language" className="sr-only">Filter by Language</label>
          <select
            id="filter-language"
            className="filter-select"
            value={filters.language || ''}
            onChange={(e) => onChangeFilter('language', e.target.value)}
          >
            <option value="">All Languages</option>
            {COMMON_LANGUAGES.map((l) => (
              <option key={`l-${l}`} value={l}>{l}</option>
            ))}
          </select>
        </div>

        {/* Quality Filter */}
        <div className="filter-select-wrap">
          <label htmlFor="filter-quality" className="sr-only">Filter by Quality</label>
          <select
            id="filter-quality"
            className="filter-select"
            value={filters.quality || ''}
            onChange={(e) => onChangeFilter('quality', e.target.value)}
          >
            <option value="">All Qualities</option>
            {COMMON_QUALITIES.map((q) => (
              <option key={`q-${q}`} value={q}>{q}</option>
            ))}
          </select>
        </div>

        {/* Sort Filter */}
        <div className="filter-select-wrap sort">
          <ArrowUpDown size={14} className="sort-icon" />
          <label htmlFor="filter-sort" className="sr-only">Sort By</label>
          <select
            id="filter-sort"
            className="filter-select"
            value={filters.sort || 'recent'}
            onChange={(e) => onChangeFilter('sort', e.target.value)}
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={`s-${opt.value}`} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        {/* Reset Filter Button */}
        {hasActiveFilters && (
          <button
            type="button"
            className="btn-clear-filters"
            onClick={onClearFilters}
            aria-label="Clear all active filters"
          >
            Reset
          </button>
        )}
      </div>

      {totalCount !== undefined && (
        <span className="filter-results-count">
          {totalCount.toLocaleString()} {totalCount === 1 ? 'match' : 'matches'}
        </span>
      )}
    </div>
  );
};

