import React from 'react';

interface PlayerLoadingProps {
  label?: string;
}

export const PlayerLoading: React.FC<PlayerLoadingProps> = ({
  label = 'Resolving stream from high-speed servers…',
}) => {
  return (
    <div className="player-loading-overlay">
      <div className="player-spinner" />
      <p className="player-loading-text">{label}</p>
    </div>
  );
};

