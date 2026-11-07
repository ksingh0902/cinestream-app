import React from 'react';
import { Check, Play, Pause } from 'lucide-react';
import { EpisodeItem } from '../types';

interface EpisodeCardProps {
  episode: EpisodeItem;
  isActive: boolean;
  isWatched?: boolean;
  onSelect: (season: number, episode: number, movieId?: number | string | null) => void;
}

export const EpisodeCard: React.FC<EpisodeCardProps> = ({
  episode,
  isActive,
  isWatched,
  onSelect,
}) => {
  const epNum = episode.episode_number ?? episode.e;
  const sNum = episode.s;
  const sPad = String(sNum).padStart(2, '0');
  const ePad = String(epNum).padStart(2, '0');
  const title = episode.name || `Episode ${epNum}`;

  return (
    <div
      className={`episode-card ${isActive ? 'active' : ''} ${isWatched ? 'watched' : ''}`}
      onClick={() => onSelect(sNum, epNum, episode.movie_id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(sNum, epNum, episode.movie_id);
        }
      }}
      aria-label={`Season ${sNum} Episode ${epNum}: ${title}${isActive ? ' (Currently Playing)' : ''}${isWatched ? ' (Watched)' : ''}`}
    >
      <div className="ep-card-badge">
        <span className="ep-card-code">S{sPad}·E{ePad}</span>
        {isActive && <span className="ep-status-pill now-playing">Playing</span>}
        {isWatched && !isActive && (
          <span className="ep-status-pill watched">
            <Check size={11} strokeWidth={1.5} />
            <span>Watched</span>
          </span>
        )}
      </div>

      <div className="ep-card-body">
        <h4 className="ep-card-title" title={title}>
          {title}
        </h4>
      </div>

      <div className="ep-card-action">
        <span className="ep-play-icon">
          {isActive ? (
            <Pause size={14} strokeWidth={1.5} />
          ) : (
            <Play size={14} strokeWidth={1.5} fill="currentColor" />
          )}
        </span>
      </div>
    </div>
  );
};
