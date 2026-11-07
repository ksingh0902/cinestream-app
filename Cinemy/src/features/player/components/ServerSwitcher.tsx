import React from 'react';
import { Radio, Zap } from 'lucide-react';
import { StreamServer } from '../types';

interface ServerSwitcherProps {
  servers: StreamServer[];
  activeServerIndex: number;
  onSelectServer: (index: number) => void;
}

export const ServerSwitcher: React.FC<ServerSwitcherProps> = ({
  servers,
  activeServerIndex,
  onSelectServer,
}) => {
  if (!servers || servers.length <= 1) return null;

  return (
    <div className="player-server-switcher" role="radiogroup" aria-label="Streaming server selection">
      <span className="server-switcher-label">Servers:</span>
      <div className="server-pill-list">
        {servers.map((srv, idx) => {
          const isActive = idx === activeServerIndex;
          const isHls = srv.kind === 'hls';
          return (
            <button
              key={`${srv.url}-${idx}`}
              className={`server-pill-btn ${isActive ? 'active' : ''} ${isHls ? 'hls-tag' : 'embed-tag'}`}
              onClick={() => onSelectServer(idx)}
              role="radio"
              aria-checked={isActive}
              title={`Switch to ${srv.label}`}
            >
              <span className="server-pill-icon">
                {isHls ? (
                  <Radio size={13} strokeWidth={1.5} />
                ) : (
                  <Zap size={13} strokeWidth={1.5} />
                )}
              </span>
              <span className="server-pill-text">{srv.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
