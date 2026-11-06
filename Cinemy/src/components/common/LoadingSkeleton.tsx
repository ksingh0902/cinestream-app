import React from 'react';

interface LoadingSkeletonProps {
  count?: number;
}

export const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({ count = 8 }) => {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
        gap: 'var(--space-3)',
        width: '100%',
      }}
      aria-hidden="true"
    >
      {Array.from({ length: count }).map((_, idx) => (
        <div key={idx} className="skeleton-card skeleton-shimmer">
          <div className="skeleton-poster" />
          <div className="skeleton-text" />
          <div className="skeleton-text short" />
        </div>
      ))}
    </div>
  );
};

