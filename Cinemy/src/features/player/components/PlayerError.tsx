import React from 'react';
import { AlertTriangle, RotateCcw, Layers } from 'lucide-react';

interface PlayerErrorProps {
  message: string;
  onRetry?: () => void;
  onSwitchServer?: () => void;
  hasAlternateServers?: boolean;
}

export const PlayerError: React.FC<PlayerErrorProps> = ({
  message,
  onRetry,
  onSwitchServer,
  hasAlternateServers,
}) => {
  return (
    <div className="player-error-overlay">
      <div className="player-error-icon">
        <AlertTriangle size={36} strokeWidth={1.5} />
      </div>
      <h3 className="player-error-title">Playback Error</h3>
      <p className="player-error-message">{message}</p>
      <div className="player-error-actions">
        {onRetry && (
          <button className="player-btn player-btn-primary" onClick={onRetry}>
            <RotateCcw size={15} strokeWidth={1.5} />
            <span>Retry Stream</span>
          </button>
        )}
        {hasAlternateServers && onSwitchServer && (
          <button className="player-btn player-btn-secondary" onClick={onSwitchServer}>
            <Layers size={15} strokeWidth={1.5} />
            <span>Switch Server</span>
          </button>
        )}
      </div>
    </div>
  );
};
