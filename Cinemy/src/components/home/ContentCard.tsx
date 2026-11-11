import React, { useState } from 'react';
import { MovieItem } from '../../types/catalogue';
import { getPosterUrl, getPosterFallbackSvg, formatRating } from '../../utils/formatters';

interface ContentCardProps {
  movie: MovieItem;
  onSelect: (id: number, title: string) => void;
  tabIndex?: number;
  upgradeBadge?: string;
}

export const ContentCard = React.memo<ContentCardProps>(
  ({ movie, onSelect, tabIndex = 0, upgradeBadge }) => {
    const [imgSrc, setImgSrc] = useState<string>(() =>
      getPosterUrl(movie.poster || movie.poster_url, movie.title, movie.year)
    );

    const rating = formatRating(movie.rating, movie.imdb);
    const isSeries = Boolean(movie.is_series);
    const isDubbed = Boolean(movie.is_hindi_dubbed);
    const effectiveUpgradeBadge = upgradeBadge || movie.upgradeBadge || movie.latest_quality_transition;

    const handleClick = () => {
      onSelect(movie.id, movie.title);
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSelect(movie.id, movie.title);
      }
    };

    const handleImgError = () => {
      setImgSrc(getPosterFallbackSvg(movie.title, movie.year));
    };

    return (
      <div
        className="content-card"
        role="button"
        tabIndex={tabIndex}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        aria-label={`${movie.title} (${movie.year || 'Unknown Year'}), ${isSeries ? 'Series' : 'Movie'}${rating ? `, Rating: ${rating}` : ''}`}
      >
        <div className="card-poster-wrap">
          <img
            className="card-poster-img"
            src={imgSrc}
            alt={movie.title}
            loading="lazy"
            onError={handleImgError}
          />

          {/* Top-left Badges (Type & Dubbing) */}
          <div className="card-badge-top-left">
            {isSeries ? (
              <span className="badge-tag series">Series</span>
            ) : (
              <span className="badge-tag movie">Movie</span>
            )}
            {isDubbed && <span className="badge-tag dubbed">Hindi Dub</span>}
          </div>

          {/* Top-right Rating Badge */}
          {rating && (
            <div className="card-badge-top-right">
              <span className="badge-tag rating">{rating}</span>
            </div>
          )}

          {/* Quality Upgrade Transition Badge (Bottom-center overlay on poster) */}
          {effectiveUpgradeBadge && (
            <div className="card-badge-upgrade">
              <span className="badge-tag upgrade">{effectiveUpgradeBadge}</span>
            </div>
          )}
        </div>

        <div className="card-body">
          <h3 className="card-title" title={movie.title}>
            {movie.title}
          </h3>
          <div className="card-footer">
            <span className="card-year">{movie.year || '—'}</span>
            {movie.quality && <span className="card-quality">{movie.quality}</span>}
          </div>
        </div>
      </div>
    );
  },
  (prevProps, nextProps) => {
    // Only re-render when movie attributes or onSelect reference change
    return (
      prevProps.movie.id === nextProps.movie.id &&
      prevProps.movie.title === nextProps.movie.title &&
      prevProps.movie.poster === nextProps.movie.poster &&
      prevProps.movie.poster_url === nextProps.movie.poster_url &&
      prevProps.movie.rating === nextProps.movie.rating &&
      prevProps.movie.quality === nextProps.movie.quality &&
      prevProps.movie.latest_quality_transition === nextProps.movie.latest_quality_transition &&
      prevProps.movie.upgradeBadge === nextProps.movie.upgradeBadge &&
      prevProps.upgradeBadge === nextProps.upgradeBadge &&
      prevProps.movie.is_series === nextProps.movie.is_series &&
      prevProps.movie.is_hindi_dubbed === nextProps.movie.is_hindi_dubbed &&
      prevProps.onSelect === nextProps.onSelect
    );
  }
);

