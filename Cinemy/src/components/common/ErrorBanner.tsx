import React from 'react';
import { Radio, AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorBannerProps {
  message: string;
  isOutage?: boolean;
  onRetry?: () => void;
}

export const ErrorBanner: React.FC<ErrorBannerProps> = ({
  message,
  isOutage = false,
  onRetry,
}) => {
  return (
    <div className="error-banner" role="alert">
      <div className="error-banner-content">
        <span className="error-icon">{isOutage ? <Radio size={16} strokeWidth={1.5} /> : <AlertTriangle size={16} strokeWidth={1.5} />}</span>
        <div>
          <strong style={{ display: 'block', fontSize: '13px', marginBottom: '2px' }}>
            {isOutage ? 'Service Temporarily Unavailable' : 'Error'}
          </strong>
          <span className="error-message">{message}</span>
        </div>
      </div>
      {onRetry && (
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onRetry}
          style={{ padding: '4px 12px', fontSize: '12px' }}
        >
          <RefreshCw size={13} strokeWidth={1.5} /> <span>Retry</span>
        </button>
      )}
    </div>
  );
};

