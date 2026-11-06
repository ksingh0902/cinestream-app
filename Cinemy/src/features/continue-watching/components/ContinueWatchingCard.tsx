import React, { useState } from 'react';
import { Play, X, Languages } from 'lucide-react';
import { ContinueWatchingDisplayItem } from '../types';
import { getPosterFallbackSvg } from '../../../utils/formatters';

interface ContinueWatchingCardProps {
  item: ContinueWatchingDisplayItem;
  onResume: (item: ContinueWatchingDisplayItem) => void;
  onRemove: (contentId: string, seriesId?: string | null) => void;
}

export const ContinueWatchingCard: React.FC<ContinueWatchingCardProps> = ({
  item,
  onResume,
  onRemove,
}) => {
  const [imgSrc, setImgSrc] = useState<string>(item.poster);

  const handleCardClick = () => {
    onResume(item);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onResume(item);
    }
  };

  const handleRemoveClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    onRemove(item.contentId, item.seriesId);
  };

  const handleImgError = () => {
    setImgSrc(getPosterFallbackSvg(item.title, item.year));
  };

  // Provider badge color matching existing Vanilla styles
  const getProviderBadge = (source: string) => {
    const s = (source || '').toLowerCase();
    switch (s) {
      case 'ask4movie':
        return <span className="cw-card-badge ask">ASK</span>;
      case 'dooflix':
        return <span className="cw-card-badge doo">DOO</span>;
      case 'movies7':
        return <span className="cw-card-badge m7">M7</span>;
      case 'yomovies':
      default:
        return <span className="cw-card-badge ym">YM</span>;
    }
  };

  return (
    <div
      className="cw-card"
      role="button"
      tabIndex={0}
      onClick={handleCardClick}
      onKeyDown={handleKeyDown}
      aria-label={`Resume ${item.title}, ${item.metaText}`}
    >
      {/* Remove Button */}
      <button
        type="button"
        className="cw-btn-remove"
        onClick={handleRemoveClick}
        aria-label={`Remove ${item.title} from Continue Watching`}
        title="Remove from Continue Watching"
      >
        <X size={14} strokeWidth={1.5} />
      </button>

      {/* Poster Image with Progress Overlay */}
      <div className="cw-poster-wrap">
        <img
          className="cw-poster-img"
          src={imgSrc}
          alt={item.title}
          loading="lazy"
          onError={handleImgError}
        />

        {/* Hover / TV Focus Play Overlay */}
        <div className="cw-play-overlay">
          <div className="cw-play-icon"><Play size={20} strokeWidth={1.5} fill="currentColor" /></div>
        </div>

        {/* Progress Bar (0–100%) */}
        {item.displayProgressPct > 0 && (
          <div className="cw-progress-bg" aria-hidden="true">
            <div
              className="cw-progress-fill"
              style={{ width: `${item.displayProgressPct}%` }}
            />
          </div>
        )}
      </div>

      {/* Card Info Body */}
      <div className="cw-card-info">
        <div className="cw-card-title" title={item.title}>
          {item.title}
        </div>
        <div className="cw-card-meta">
          <span className="cw-meta-text">{item.metaText}</span>
          <div className="cw-meta-badges">
            {getProviderBadge(item.source)}
            {item.isHindiDubbed && <span className="cw-card-badge dub"><Languages size={10} strokeWidth={1.5} /><span>DUB</span></span>}
          </div>
        </div>
      </div>
    </div>
  );
};

