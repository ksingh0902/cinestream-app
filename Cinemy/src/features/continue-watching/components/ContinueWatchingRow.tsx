import React, { useRef, useState, useEffect, useCallback } from 'react';
import { ContinueWatchingDisplayItem } from '../types';
import { ContinueWatchingCard } from './ContinueWatchingCard';

interface ContinueWatchingRowProps {
  items: ContinueWatchingDisplayItem[];
  onResume: (item: ContinueWatchingDisplayItem) => void;
  onRemove: (contentId: string, seriesId?: string | null) => void;
}

export const ContinueWatchingRow: React.FC<ContinueWatchingRowProps> = ({
  items,
  onResume,
  onRemove,
}) => {
  const railRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const updateScrollControls = useCallback(() => {
    const el = railRef.current;
    if (!el) return;
    const hasOverflow = el.scrollWidth > el.clientWidth + 4;
    setCanScrollLeft(hasOverflow && el.scrollLeft > 4);
    setCanScrollRight(hasOverflow && el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
  }, []);

  useEffect(() => {
    updateScrollControls();
    window.addEventListener('resize', updateScrollControls);
    return () => window.removeEventListener('resize', updateScrollControls);
  }, [items, updateScrollControls]);

  const handleScroll = (direction: 'left' | 'right') => {
    const el = railRef.current;
    if (!el) return;
    const scrollAmount = Math.max(240, Math.floor(el.clientWidth * 0.72));
    el.scrollBy({
      left: direction === 'left' ? -scrollAmount : scrollAmount,
      behavior: 'smooth',
    });
    setTimeout(updateScrollControls, 280);
  };

  return (
    <div className="cw-row-wrapper">
      {/* Scroll Left Arrow */}
      {canScrollLeft && (
        <button
          type="button"
          className="cw-rail-arrow left"
          onClick={() => handleScroll('left')}
          aria-label="Scroll Continue Watching Left"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </button>
      )}

      {/* Horizontal Carousel */}
      <div
        className="cw-carousel"
        ref={railRef}
        onScroll={updateScrollControls}
        role="region"
        aria-label="Continue Watching carousel"
      >
        {items.map((item) => (
          <ContinueWatchingCard
            key={item.contentId}
            item={item}
            onResume={onResume}
            onRemove={onRemove}
          />
        ))}
      </div>

      {/* Scroll Right Arrow */}
      {canScrollRight && (
        <button
          type="button"
          className="cw-rail-arrow right"
          onClick={() => handleScroll('right')}
          aria-label="Scroll Continue Watching Right"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M9 18l6-6-6-6" />
          </svg>
        </button>
      )}
    </div>
  );
};

