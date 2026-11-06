import React from 'react';

interface LoadingSpinnerProps {
  label?: string;
  size?: 'sm' | 'md' | 'lg';
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  label = 'Loading...',
  size = 'md',
}) => {
  const sizeMap = {
    sm: { width: '20px', height: '20px', borderWidth: '2px' },
    md: { width: '36px', height: '36px', borderWidth: '3px' },
    lg: { width: '48px', height: '48px', borderWidth: '4px' },
  };

  return (
    <div className="spinner-container" role="status" aria-live="polite">
      <div className="spinner" style={sizeMap[size]} />
      {label && <span style={{ color: 'var(--dim)', fontSize: '13px' }}>{label}</span>}
    </div>
  );
};

