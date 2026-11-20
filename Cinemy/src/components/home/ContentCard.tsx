import React, { useState, useEffect, useMemo, useRef } from 'react';
import { MovieItem } from '../../types/catalogue';
import { getPosterCandidates, getPosterFallbackSvg, formatRating } from '../../utils/formatters';
import { resolvePosterFallback } from '../../api/catalogue';

export type PosterLoadState = 'idle' | 'loading' | 'loaded' | 'error';

interface ContentCardProps {
  movie: MovieItem;
  onSelect: (id: number, title: string) => void;
  tabIndex?: number;
  upgradeBadge?: string;
}

export const ContentCard = React.memo<ContentCardProps>(
  ({ movie, onSelect, tabIndex = 0, upgradeBadge }) => {
    const fallbackSvg = useMemo(
      () => getPosterFallbackSvg(movie.title, movie.year),
      [movie.title, movie.year]
    );

    const fallbacksKey = (movie.poster_fallbacks || []).join('|');
    const candidates = useMemo(
      () => getPosterCandidates(movie.poster, movie.poster_url, movie.poster_fallbacks),
      [movie.poster, movie.poster_url, fallbacksKey]
    );
    const candidatesKey = candidates.join('|');

    const [candidateIdx, setCandidateIdx] = useState<number>(0);
    const [resolvedUrl, setResolvedUrl] = useState<string | null>(null);
    const [remoteAttempted, setRemoteAttempted] = useState<boolean>(false);
    const [loadState, setLoadState] = useState<PosterLoadState>(() =>
      candidates.length > 0 ? 'loading' : 'error'
    );
    const imgRef = useRef<HTMLImageElement | null>(null);
    const isMountedRef = useRef<boolean>(true);

    useEffect(() => {
      isMountedRef.current = true;
      return () => {
        isMountedRef.current = false;
      };
    }, []);

    // Reset image lifecycle cleanly when poster URLs change for this card
    useEffect(() => {
      setCandidateIdx(0);
      setResolvedUrl(null);
      setRemoteAttempted(false);
      setLoadState(candidates.length > 0 ? 'loading' : 'error');
    }, [candidatesKey, candidates.length]);

    const activeSrc =
      loadState === 'error'
        ? fallbackSvg
        : resolvedUrl
        ? resolvedUrl
        : candidateIdx < candidates.length
        ? candidates[candidateIdx]
        : fallbackSvg;

    // Handle images already resolved in browser cache before React attaches onLoad
    useEffect(() => {
      const img = imgRef.current;
      if (!img || loadState !== 'loading') return;
      if (img.complete && img.naturalWidth > 0) {
        setLoadState('loaded');
      }
    }, [activeSrc, loadState]);

    const rating = formatRating(movie.rating, movie.imdb);
    const isSeries = Boolean(movie.is_series);
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

    const handleImgLoad = () => {
      if (loadState !== 'error') {
        setLoadState('loaded');
      }
    };

    const handleImgError = () => {
      if (loadState === 'error') return;

      // 1. Advance through DB mirror fallbacks first (zero extra API traffic)
      if (!resolvedUrl && candidateIdx + 1 < candidates.length) {
        setCandidateIdx((prev) => prev + 1);
        setLoadState('loading');
        return;
      }

      // 2. If all DB candidates failed, attempt ONE bounded on-demand backend poster resolve
      if (!remoteAttempted && movie.title) {
        setRemoteAttempted(true);
        resolvePosterFallback({
          title: movie.title,
          year: movie.year,
          is_series: movie.is_series,
        }).then((url) => {
          if (!isMountedRef.current) return;
          if (url && !candidates.includes(url)) {
            setResolvedUrl(url);
            setLoadState('loading');
          } else {
            setLoadState('error');
          }
        });
        return;
      }

      // 3. Permanent failure -> terminate loading and display CINEMY SVG placeholder
      setLoadState('error');
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
        <div className="card-poster-wrap" data-poster-state={loadState}>
          <img
            ref={imgRef}
            className="card-poster-img"
            src={activeSrc}
            alt={movie.title}
            loading="lazy"
            onLoad={handleImgLoad}
            onError={handleImgError}
          />

          {/* Top-left Badge (Type) */}
          <div className="card-badge-top-left">
            {isSeries ? (
              <span className="badge-tag series">Series</span>
            ) : (
              <span className="badge-tag movie">Movie</span>
            )}
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
      (prevProps.movie.poster_fallbacks || []).join('|') === (nextProps.movie.poster_fallbacks || []).join('|') &&
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

