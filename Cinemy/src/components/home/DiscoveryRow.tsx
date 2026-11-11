import React, { useRef } from 'react';
import { ChevronLeft, ChevronRight, ArrowRight } from 'lucide-react';
import { MovieItem } from '../../types/catalogue';
import { ContentCard } from './ContentCard';
import { LoadingSkeleton } from '../common/LoadingSkeleton';

interface DiscoveryRowProps {
  id: string;
  title: string;
  icon?: React.ReactNode;
  count?: number;
  items: MovieItem[];
  loading?: boolean;
  emptyMessage?: string;
  onSelectMovie: (id: number, title: string) => void;
  onSeeAll?: () => void;
  seeAllLabel?: string;
  isUpgradeRow?: boolean;
}

export const DiscoveryRow: React.FC<DiscoveryRowProps> = ({
  id,
  title,
  icon,
  count,
  items,
  loading = false,
  emptyMessage = 'No titles found in this section.',
  onSelectMovie,
  onSeeAll,
  seeAllLabel = 'See All',
  isUpgradeRow = false,
}) => {
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);

  const handleScroll = (direction: 'left' | 'right') => {
    if (!scrollContainerRef.current) return;
    const container = scrollContainerRef.current;
    const cardWidth = 175; // Approx card width + gap
    const scrollAmount = direction === 'left' ? -cardWidth * 3 : cardWidth * 3;
    container.scrollBy({ left: scrollAmount, behavior: 'smooth' });
  };

  return (
    <section className="discovery-section" id={id} aria-label={title}>
      {/* Section Header */}
      <div className="discovery-header">
        <div className="discovery-title-group">
          {icon && <span className="discovery-icon">{icon}</span>}
          <h2 className="discovery-heading">{title}</h2>
          {count !== undefined && count > 0 && (
            <span className="discovery-count-badge">{count}</span>
          )}
        </div>

        <div className="discovery-actions">
          {onSeeAll && (
            <button
              type="button"
              className="discovery-btn-see-all"
              onClick={onSeeAll}
              aria-label={`${seeAllLabel} for ${title}`}
            >
              <span>{seeAllLabel}</span>
              <ArrowRight size={14} strokeWidth={2} />
            </button>
          )}

          <div className="discovery-nav-buttons">
            <button
              type="button"
              className="discovery-nav-btn left"
              onClick={() => handleScroll('left')}
              aria-label={`Scroll ${title} left`}
            >
              <ChevronLeft size={20} strokeWidth={2} />
            </button>
            <button
              type="button"
              className="discovery-nav-btn right"
              onClick={() => handleScroll('right')}
              aria-label={`Scroll ${title} right`}
            >
              <ChevronRight size={20} strokeWidth={2} />
            </button>
          </div>
        </div>
      </div>

      {/* Row Content */}
      {loading ? (
        <div className="discovery-row-loading">
          <LoadingSkeleton count={6} />
        </div>
      ) : items.length === 0 ? (
        <div className="discovery-empty-state">
          <p>{emptyMessage}</p>
        </div>
      ) : (
        <div className="discovery-row-track" ref={scrollContainerRef}>
          {items.map((movie, idx) => (
            <div key={`${id}-card-${movie.id}-${idx}`} className="discovery-card-wrapper">
              <ContentCard
                movie={movie}
                onSelect={onSelectMovie}
                upgradeBadge={isUpgradeRow ? (movie.latest_quality_transition || movie.upgradeBadge || 'HD UPGRADE') : undefined}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

