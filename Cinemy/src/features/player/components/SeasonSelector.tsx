import React from 'react';
import { SeasonItem } from '../types';

interface SeasonSelectorProps {
  seasons: SeasonItem[];
  activeSeason: number;
  onSelectSeason: (seasonNumber: number) => void;
}

export const SeasonSelector: React.FC<SeasonSelectorProps> = ({
  seasons,
  activeSeason,
  onSelectSeason,
}) => {
  if (!seasons || seasons.length <= 1) return null;

  return (
    <div className="season-selector-bar" role="tablist" aria-label="Select TV Season">
      {seasons.map((s) => {
        const isActive = Number(s.season_number) === Number(activeSeason);
        const label = s.name || `Season ${s.season_number}`;
        const count = s.episode_count || s.episodes?.length || 0;

        return (
          <button
            key={`season-${s.season_number}`}
            className={`season-tab-btn ${isActive ? 'active' : ''}`}
            onClick={() => onSelectSeason(s.season_number)}
            role="tab"
            aria-selected={isActive}
            title={`${label} (${count} Episodes)`}
          >
            <span className="season-tab-name">{label}</span>
            <span className="season-tab-count">{count} eps</span>
          </button>
        );
      })}
    </div>
  );
};

