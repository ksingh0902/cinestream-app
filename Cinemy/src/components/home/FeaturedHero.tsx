import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Play,
  Bookmark,
  Check,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Tv,
  Clapperboard,
  Languages,
  Star,
} from 'lucide-react';
import { MovieItem } from '../../types/catalogue';
import { getPosterUrl, formatRating } from '../../utils/formatters';
import { resolveBackdrop } from '../../api/catalogue';
import { useWatchlist } from '../../features/watchlist';

function upgradeBackdropResolution(url: string): string {
  if (!url || url.startsWith('data:')) return url;
  // Upgrade low-res TMDB thumbnails (e.g. w185/w300/w342/w400/w500/w780) to crisp w1280 for full-bleed hero display
  if (url.includes('image.tmdb.org/t/p/')) {
    return url.replace(/\/t\/p\/w\d+\//i, '/t/p/w1280/');
  }
  // Upgrade resized Amazon/IMDb thumbnails to high-res widescreen width
  if (url.includes('m.media-amazon.com') && /\._V1_[^.]+\.jpg$/i.test(url)) {
    return url.replace(/\._V1_[^.]+\.jpg$/i, '._V1_QL85_UX1280_.jpg');
  }
  return url;
}

interface FeaturedHeroProps {
  items: MovieItem[];
  onPlay: (id: number, title: string) => void;
  onMyList: (id: number, title: string) => void;
}

export const FeaturedHero: React.FC<FeaturedHeroProps> = ({ items, onPlay, onMyList }) => {
  const { isInList } = useWatchlist();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [isFading, setIsFading] = useState(false);
  const [resolvedBackdrops, setResolvedBackdrops] = useState<Record<number, string>>({});

  const timerRef = useRef<number | null>(null);
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);
  const totalItems = items.length;

  // Pre-resolve crisp 16:9 widescreen backdrops for featured hero slides (non-blocking, session-cached)
  useEffect(() => {
    if (totalItems === 0) return;
    let cancelled = false;

    items.forEach((item) => {
      if ((item as any).backdrop || (item as any).backdrop_url) return;
      void resolveBackdrop({
        title: item.title,
        year: item.year,
        is_series: item.is_series,
        tmdb_id: (item as any).tmdb_id,
      }).then((url) => {
        if (!cancelled && url) {
          setResolvedBackdrops((prev) => (prev[item.id] === url ? prev : { ...prev, [item.id]: url }));
        }
      });
    });

    return () => {
      cancelled = true;
    };
  }, [items, totalItems]);

  const goToNext = useCallback(() => {
    if (totalItems <= 1) return;
    setIsFading(true);
    setTimeout(() => {
      setCurrentIndex((prev) => (prev + 1) % totalItems);
      setIsFading(false);
    }, 280);
  }, [totalItems]);

  const goToPrev = useCallback(() => {
    if (totalItems <= 1) return;
    setIsFading(true);
    setTimeout(() => {
      setCurrentIndex((prev) => (prev - 1 + totalItems) % totalItems);
      setIsFading(false);
    }, 280);
  }, [totalItems]);

  const resetTimer = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (!isPaused && totalItems > 1) {
      timerRef.current = window.setInterval(goToNext, 2000);
    }
  }, [goToNext, isPaused, totalItems]);

  const handleManualNext = () => {
    goToNext();
    resetTimer();
  };

  const handleManualPrev = () => {
    goToPrev();
    resetTimer();
  };

  const handleDotClick = (idx: number) => {
    if (idx === currentIndex || totalItems <= 1) return;
    setIsFading(true);
    setTimeout(() => {
      setCurrentIndex(idx);
      setIsFading(false);
    }, 280);
    resetTimer();
  };

  const handleTouchStart = (e: React.TouchEvent<HTMLElement>) => {
    if (totalItems <= 1 || e.touches.length !== 1) return;
    touchStartRef.current = {
      x: e.touches[0].clientX,
      y: e.touches[0].clientY,
    };
  };

  const handleTouchEnd = (e: React.TouchEvent<HTMLElement>) => {
    if (!touchStartRef.current || totalItems <= 1 || e.changedTouches.length !== 1) {
      touchStartRef.current = null;
      return;
    }
    const deltaX = e.changedTouches[0].clientX - touchStartRef.current.x;
    const deltaY = e.changedTouches[0].clientY - touchStartRef.current.y;
    touchStartRef.current = null;

    // Trigger slide only on deliberate horizontal swipe (avoid interfering with vertical scroll or taps)
    if (Math.abs(deltaX) > 40 && Math.abs(deltaX) > Math.abs(deltaY) * 1.2) {
      if (deltaX < 0) {
        handleManualNext();
      } else {
        handleManualPrev();
      }
    }
  };

  const handleTouchCancel = () => {
    touchStartRef.current = null;
  };

  // Automatic rotation timer — EXACTLY 2000ms per featured item
  useEffect(() => {
    if (totalItems <= 1) return;

    // Respect reduced motion preference
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (mediaQuery.matches) {
      return;
    }

    if (isPaused) {
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }

    timerRef.current = window.setInterval(goToNext, 2000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [totalItems, isPaused, goToNext]);

  // Pause rotation when browser tab is inactive (document.hidden)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) {
        setIsPaused(true);
      } else {
        setIsPaused(false);
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, []);

  if (totalItems === 0) {
    return null;
  }

  const current = items[currentIndex];
  const posterUrl = getPosterUrl(current.poster || current.poster_url, current.title, current.year);

  // Prefer verified 16:9 widescreen backdrop (from item or cached TMDb lookup), falling back to upgraded HD poster
  const backdropUrl =
    (current as any).backdrop ||
    (current as any).backdrop_url ||
    resolvedBackdrops[current.id] ||
    upgradeBackdropResolution(posterUrl);

  const rating = formatRating(current.rating, current.imdb);
  const isSeries = Boolean(current.is_series);
  const isDubbed = Boolean(current.is_hindi_dubbed);
  const isSavedInWatchlist = isInList(current.id);

  const genresText = Array.isArray(current.genres) && current.genres.length > 0
    ? current.genres.slice(0, 3).join(' • ')
    : null;

  const synopsisText = current.synopsis
    ? current.synopsis
    : `Experience ${current.title} streaming now in high resolution across high-speed servers.`;

  return (
    <section
      className="hero-fullbleed"
      aria-label="Featured Spotlight"
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={handleTouchCancel}
    >
      {/* Full-Bleed Crisp Widescreen Backdrop Layer with very slow zoom effect */}
      <div className="hero-backdrop-stage" aria-hidden="true">
        <img
          className={`hero-backdrop-img ken-burns ${isFading ? 'fading' : ''}`}
          src={backdropUrl}
          alt=""
          loading="eager"
          decoding="async"
        />
      </div>

      {/* Cinematic Gradient Overlays: Dark left-to-right (solid left, transparent right) & bottom fade */}
      <div className="hero-gradient-overlay-left" aria-hidden="true" />
      <div className="hero-gradient-overlay-bottom" aria-hidden="true" />
      <div className="hero-gradient-overlay-top" aria-hidden="true" />

      {/* Main Hero Content Composition */}
      <div className="hero-inner-container">
        <div
          className={`hero-content-wrapper ${isFading ? 'fade-out' : 'fade-in'}`}
        >
          {/* Left: Metadata, Display Title, CTAs & Dots */}
          <div className="hero-info-column">
            {/* Category / Type Badge Row */}
            <div className="hero-badges-row">
              <span className="hero-badge hero-badge-spotlight">
                <Sparkles size={13} strokeWidth={1.5} />
                <span>Featured Spotlight</span>
              </span>
              <span className="hero-badge hero-badge-type">
                {isSeries ? (
                  <>
                    <Tv size={13} strokeWidth={1.5} />
                    <span>Series</span>
                  </>
                ) : (
                  <>
                    <Clapperboard size={13} strokeWidth={1.5} />
                    <span>Movie</span>
                  </>
                )}
              </span>
              {isDubbed && (
                <span className="hero-badge hero-badge-dub">
                  <Languages size={13} strokeWidth={1.5} />
                  <span>Hindi Dubbed</span>
                </span>
              )}
            </div>

            {/* Display Title — reduced weight (700) and slightly smaller */}
            <h1 className="hero-display-title" title={current.title}>
              {current.title}
            </h1>

            {/* Metadata Badges with small orange star icon */}
            <div className="hero-meta-row">
              {rating && (
                <span className="hero-meta-rating">
                  <Star size={13} strokeWidth={1.5} className="star-icon" fill="var(--accent)" color="var(--accent)" />
                  <span className="rating-num">{rating}</span>
                </span>
              )}
              {current.year && <span className="hero-meta-year">{current.year}</span>}
              {genresText && <span className="hero-meta-genres">{genresText}</span>}
              {current.quality && <span className="hero-meta-quality">{current.quality}</span>}
            </div>

            {/* Synopsis Description */}
            <p className="hero-synopsis-text">{synopsisText}</p>

            {/* Action CTA Buttons */}
            <div
              className="hero-action-buttons"
              onMouseEnter={() => setIsPaused(true)}
              onMouseLeave={() => setIsPaused(false)}
              onFocus={() => setIsPaused(true)}
              onBlur={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                  setIsPaused(false);
                }
              }}
            >
              <button
                type="button"
                className="btn btn-primary btn-hero-play"
                onClick={() => onPlay(current.id, current.title)}
                aria-label={`Play ${current.title}`}
              >
                <Play size={18} strokeWidth={1.5} fill="currentColor" />
                <span>Play Now</span>
              </button>

              <button
                type="button"
                className={`btn btn-secondary btn-hero-watchlist ${isSavedInWatchlist ? 'active' : ''}`}
                onClick={() => onMyList(current.id, current.title)}
                aria-label={isSavedInWatchlist ? `Remove ${current.title} from My List` : `Add ${current.title} to My List`}
              >
                {isSavedInWatchlist ? (
                  <>
                    <Check size={17} strokeWidth={1.5} />
                    <span>In My List</span>
                  </>
                ) : (
                  <>
                    <Bookmark size={17} strokeWidth={1.5} />
                    <span>Add to List</span>
                  </>
                )}
              </button>
            </div>

            {/* Slide Pagination Dots — positioned safely under the action buttons */}
            {totalItems > 1 && (
              <div
                className="hero-pagination-bar"
                role="tablist"
                aria-label="Featured Titles"
                onKeyDown={(e) => {
                  if (e.key === 'ArrowRight') {
                    e.preventDefault();
                    handleManualNext();
                  } else if (e.key === 'ArrowLeft') {
                    e.preventDefault();
                    handleManualPrev();
                  }
                }}
              >
                {items.map((item, idx) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`hero-dot-indicator ${idx === currentIndex ? 'active' : ''}`}
                    onClick={() => handleDotClick(idx)}
                    aria-label={`Featured item ${idx + 1}: ${item.title}`}
                    aria-selected={idx === currentIndex}
                    role="tab"
                  />
                ))}
              </div>
            )}
          </div>

          {/* Right: Comfortably Padded & Scaled Featured Poster Card */}
          <div className="hero-poster-column">
            <div className="hero-poster-card" onClick={() => onPlay(current.id, current.title)}>
              <img
                className="hero-poster-artwork"
                src={posterUrl}
                alt={current.title}
                loading="eager"
              />
              <div className="hero-poster-hover-overlay">
                <div className="hero-poster-play-badge">
                  <Play size={24} strokeWidth={1.5} fill="currentColor" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Manual Navigation Arrows — Inside shared layout container edges */}
      {totalItems > 1 && (
        <div className="hero-nav-arrows" aria-hidden="true">
          <button
            type="button"
            className="hero-arrow-btn prev"
            onClick={handleManualPrev}
            aria-label="Previous Featured Title"
          >
            <ChevronLeft size={22} strokeWidth={1.5} />
          </button>
          <button
            type="button"
            className="hero-arrow-btn next"
            onClick={handleManualNext}
            aria-label="Next Featured Title"
          >
            <ChevronRight size={22} strokeWidth={1.5} />
          </button>
        </div>
      )}
    </section>
  );
};
