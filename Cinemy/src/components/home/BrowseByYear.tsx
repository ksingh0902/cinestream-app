import React from 'react';
import { Calendar } from 'lucide-react';
import { YearCountItem } from '../../types/catalogue';

interface BrowseByYearProps {
  years: YearCountItem[];
  olderCount?: number;
  selectedYear?: string | null;
  onSelectYear: (year: string) => void;
  loading?: boolean;
}

export const BrowseByYear: React.FC<BrowseByYearProps> = ({
  years,
  olderCount = 0,
  selectedYear,
  onSelectYear,
  loading = false,
}) => {
  // Take top recent 8 years for prominent compact display, plus Older
  const recentYears = years.slice(0, 8);

  if (loading) {
    return (
      <section className="browse-year-section" aria-label="Browse by Release Year">
        <div className="discovery-header">
          <div className="discovery-title-group">
            <span className="discovery-icon"><Calendar size={18} /></span>
            <h2 className="discovery-heading">Browse by Release Year</h2>
          </div>
        </div>
        <div className="browse-year-loading">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={`year-skel-${i}`} className="year-pill-skeleton" />
          ))}
        </div>
      </section>
    );
  }

  if (years.length === 0) {
    return null;
  }

  return (
    <section className="browse-year-section" aria-label="Browse by Release Year">
      <div className="discovery-header">
        <div className="discovery-title-group">
          <span className="discovery-icon"><Calendar size={18} strokeWidth={2} /></span>
          <h2 className="discovery-heading">Browse by Release Year</h2>
        </div>
      </div>

      <div className="browse-year-chips" role="group" aria-label="Release Years">
        {recentYears.map((item) => {
          const isSelected = selectedYear === item.year;
          return (
            <button
              key={`year-chip-${item.year}`}
              type="button"
              className={`year-chip${isSelected ? ' active' : ''}`}
              onClick={() => onSelectYear(item.year)}
              aria-pressed={isSelected}
              aria-label={`Year ${item.year} (${item.count.toLocaleString()} titles)`}
            >
              <span className="year-number">{item.year}</span>
              <span className="year-count">{item.count.toLocaleString()}</span>
            </button>
          );
        })}

        {olderCount > 0 && (
          <button
            type="button"
            className={`year-chip older${selectedYear === 'older' ? ' active' : ''}`}
            onClick={() => onSelectYear('older')}
            aria-pressed={selectedYear === 'older'}
            aria-label={`Older classic cinema (${olderCount.toLocaleString()} titles)`}
          >
            <span className="year-number">Older</span>
            <span className="year-count">{olderCount.toLocaleString()}</span>
          </button>
        )}
      </div>
    </section>
  );
};

