import React from 'react';
import { useContinueWatching } from '../hooks/useContinueWatching';
import { ContinueWatchingRow } from './ContinueWatchingRow';
import { ContinueWatchingDisplayItem } from '../types';

interface ContinueWatchingSectionProps {
  onResume: (item: ContinueWatchingDisplayItem) => void;
}

export const ContinueWatchingSection: React.FC<ContinueWatchingSectionProps> = ({ onResume }) => {
  const { items, count, removeItem, clearAll } = useContinueWatching();

  // If there are no in-progress records, hide the section entirely
  if (count === 0) {
    return null;
  }

  const handleClearAll = () => {
    if (
      window.confirm(
        'Clear all viewing progress saved in this browser? This only affects this device and will not affect other viewers sharing this account.'
      )
    ) {
      clearAll();
    }
  };

  return (
    <section className="cw-section" aria-label="Continue Watching">
      {/* Section Header */}
      <div className="cw-header">
        <div className="cw-title-group">
          <h2 className="cw-heading">Continue Watching</h2>
          <span className="cw-count-badge">{count}</span>
        </div>
        <button
          type="button"
          className="cw-btn-clear"
          onClick={handleClearAll}
          aria-label="Clear all viewing progress"
        >
          Clear History
        </button>
      </div>

      {/* Horizontal Carousel Row */}
      <ContinueWatchingRow
        items={items}
        onResume={onResume}
        onRemove={removeItem}
      />
    </section>
  );
};

