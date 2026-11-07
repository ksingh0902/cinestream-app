import React, { useState, useEffect, useMemo } from 'react';
import { ArrowLeft, Star, Clock, Play, Check, Bookmark, AlertTriangle } from 'lucide-react';
import { MovieItem } from '../../types/catalogue';
import { getMovie, getMovies } from '../../api/catalogue';
import { useRouter } from '../../router';
import { useWatchlist } from '../watchlist';
import { useAuth } from '../../context/AuthContext';
import {
  resolveContinueWatchingKey,
  readContinueWatchingRecords,
} from '../continue-watching/storage';
import { ContinueWatchingRecord } from '../continue-watching/types';
import { PlaybackTarget } from '../player';
import { getPosterUrl, formatRating, formatDuration } from '../../utils/formatters';
import { LoadingSpinner } from '../../components/common/LoadingSpinner';

interface MovieDetailPageProps {
  movieId: number;
  onPlayTarget: (target: PlaybackTarget) => void;
}

export const MovieDetailPage: React.FC<MovieDetailPageProps> = ({ movieId, onPlayTarget }) => {
  const { navigate, back } = useRouter();
  const { isInList, addItem, removeItem } = useWatchlist();
  const { username, role, authenticated } = useAuth();

  const [movie, setMovie] = useState<MovieItem | null>(null);
  const [recommendations, setRecommendations] = useState<MovieItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isSynopsisExpanded, setIsSynopsisExpanded] = useState<boolean>(false);

  // Check Continue Watching for saved progress
  const scopedCwKey = useMemo(() => {
    return resolveContinueWatchingKey(username, role, authenticated);
  }, [username, role, authenticated]);

  const continueWatchingRecord = useMemo<ContinueWatchingRecord | null>(() => {
    if (!movie) return null;
    const records = readContinueWatchingRecords(scopedCwKey);
    const midStr = String(movie.id);
    return (
      records.find(
        (r) =>
          r.id === movie.id ||
          r.movie_id === movie.id ||
          r.contentId === midStr ||
          r.contentId === `movie_${midStr}`
      ) || null
    );
  }, [movie, scopedCwKey]);

  // Fetch movie metadata
  useEffect(() => {
    let isCurrent = true;
    setLoading(true);
    setError(null);

    getMovie(movieId)
      .then((data) => {
        if (!isCurrent) return;
        setMovie(data);

        // Fetch related recommendations based on primary genre
        const primaryGenre = data.genres && data.genres[0] ? data.genres[0] : undefined;
        return getMovies({ genre: primaryGenre, per_page: 12 });
      })
      .then((recRes) => {
        if (!isCurrent || !recRes) return;
        const related = (recRes.items || []).filter((item) => item.id !== movieId);
        setRecommendations(related);
      })
      .catch((err: any) => {
        if (!isCurrent) return;
        console.error('Failed to load movie details:', err);
        setError(err.message || 'Unable to retrieve title details.');
      })
      .finally(() => {
        if (isCurrent) setLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [movieId]);

  if (loading) {
    return (
      <div className="detail-loading-container">
        <LoadingSpinner label="Loading title details..." size="lg" />
      </div>
    );
  }

  if (error || !movie) {
    return (
      <div className="detail-error-container">
        <div className="error-icon"><AlertTriangle size={36} strokeWidth={1.5} /></div>
        <h2 className="error-title">{error ? 'Failed to Load Title' : 'Title Not Found'}</h2>
        <p className="error-desc">
          {error || `No movie or series was found with ID #${movieId}. It may have been removed or updated.`}
        </p>
        <div className="error-actions">
          <button type="button" className="btn btn-primary" onClick={() => back()}>
            ← Go Back
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => navigate('/')}>
            Explore Catalogue
          </button>
        </div>
      </div>
    );
  }

  const isSaved = isInList(movie.id);
  const ratingBadge = formatRating(movie.rating, movie.imdb);
  const isSeries = Boolean(movie.is_series);
  const isDubbed = Boolean(movie.is_hindi_dubbed);

  const formattedRuntime = movie.duration_s
    ? formatDuration(movie.duration_s)
    : movie.duration || null;

  const handlePlayClick = () => {
    const resumeTime = continueWatchingRecord?.currentTime || 0;
    const target: PlaybackTarget = {
      id: movie.id,
      title: movie.title,
      year: movie.year,
      poster: movie.poster || movie.poster_url,
      isSeries: isSeries,
      source: movie.source || 'yomovies',
      isHindiDubbed: isDubbed,
      duration_s: movie.duration_s,
      resumeTime,
    };
    onPlayTarget(target);
  };

  const handleToggleWatchlist = () => {
    if (isSaved) {
      removeItem(movie.id);
    } else {
      addItem({
        id: movie.id,
        title: movie.title,
        year: movie.year,
        poster: movie.poster || movie.poster_url || null,
        is_series: isSeries,
        rating: movie.rating,
        imdb: movie.imdb,
        genres: movie.genres,
        quality: movie.quality,
        source: movie.source,
      });
    }
  };

  const posterImg = getPosterUrl(movie.poster || movie.poster_url, movie.title, movie.year);
  const synopsisText = movie.synopsis || '';
  const isSynopsisLong = synopsisText.length > 260;

  return (
    <div className="title-detail-container">
      {/* Back Navigation Button */}
      <div className="detail-nav-bar">
        <button type="button" className="btn-nav-back" onClick={back} title="Go back to previous page">
          <ArrowLeft size={16} strokeWidth={1.5} /><span>Back</span>
        </button>
      </div>

      {/* Hero Spotlight Section */}
      <div className="detail-hero-section">
        {/* Backdrop Backdrop with Dark Gradients */}
        <div
          className="detail-hero-backdrop"
          style={{ backgroundImage: `url(${posterImg})` }}
          aria-hidden="true"
        />
        <div className="detail-hero-overlay" />

        <div className="detail-hero-content">
          {/* Poster Column */}
          <div className="detail-poster-wrap">
            <img src={posterImg} alt={movie.title} className="detail-poster-img" />
          </div>

          {/* Metadata & Actions Column */}
          <div className="detail-info-wrap">
            <div className="detail-badge-row">
              <span className={`badge-tag ${isSeries ? 'series' : 'movie'}`}>
                {isSeries ? 'Series' : 'Movie'}
              </span>
              {isDubbed && <span className="badge-tag dubbed">Hindi Dub</span>}
              {movie.quality && <span className="badge-tag quality">{movie.quality}</span>}
              {ratingBadge && <span className="badge-tag rating"><Star size={12} strokeWidth={1.5} fill="currentColor" /> {ratingBadge}</span>}
              {movie.audio_edition && (
                <span className="badge-tag edition">{movie.audio_edition.replace('_', ' ')}</span>
              )}
            </div>

            <h1 className="detail-title">{movie.title}</h1>

            <div className="detail-meta-row">
              {movie.year && <span className="meta-item">{movie.year}</span>}
              {formattedRuntime && <span className="meta-item"><Clock size={13} strokeWidth={1.5} /> {formattedRuntime}</span>}
              {movie.source && (
                <span className="meta-item meta-source">Source: {movie.source.toUpperCase()}</span>
              )}
            </div>

            {/* Genre Chips */}
            {movie.genres && movie.genres.length > 0 && (
              <div className="detail-genre-chips">
                {movie.genres.map((genre) => (
                  <button
                    key={genre}
                    type="button"
                    className="genre-chip"
                    onClick={() => navigate(`/genre/${encodeURIComponent(genre)}`)}
                  >
                    {genre}
                  </button>
                ))}
              </div>
            )}

            {/* Action Buttons */}
            <div className="detail-actions-row">
              <button
                type="button"
                className="btn btn-primary btn-play-large"
                onClick={handlePlayClick}
              >
                {continueWatchingRecord && continueWatchingRecord.currentTime > 10 ? (
                  <>
                    <Play size={16} strokeWidth={1.5} fill="currentColor" style={{ verticalAlign: "middle", marginRight: 6 }} /> Resume (
                    {Math.round(continueWatchingRecord.progressPct || 0)}%)
                  </>
                ) : (
                  <>
                    <Play size={16} strokeWidth={1.5} fill="currentColor" style={{ verticalAlign: "middle", marginRight: 6 }} /> Play Movie
                  </>
                )}
              </button>

              <button
                type="button"
                className={`btn btn-secondary btn-watchlist-toggle ${isSaved ? 'in-watchlist' : ''}`}
                onClick={handleToggleWatchlist}
              >
                {isSaved ? (<><Check size={16} strokeWidth={1.5} /> <span>In My List</span></>) : (<><Bookmark size={16} strokeWidth={1.5} /> <span>Add to List</span></>)}
              </button>
            </div>

            {/* Synopsis */}
            <div className="detail-synopsis-box">
              <h3 className="synopsis-label">Overview</h3>
              {synopsisText ? (
                <p className="synopsis-text">
                  {isSynopsisLong && !isSynopsisExpanded
                    ? `${synopsisText.slice(0, 260)}…`
                    : synopsisText}
                  {isSynopsisLong && (
                    <button
                      type="button"
                      className="btn-synopsis-expand"
                      onClick={() => setIsSynopsisExpanded(!isSynopsisExpanded)}
                    >
                      {isSynopsisExpanded ? ' Show Less' : ' Read More'}
                    </button>
                  )}
                </p>
              ) : (
                <p className="synopsis-empty">
                  No synopsis is available in the catalogue for this release.
                </p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Metadata Facts Grid */}
      <div className="detail-metadata-grid">
        {movie.director && (
          <div className="metadata-field">
            <span className="field-label">Director</span>
            <span className="field-value">
              {Array.isArray(movie.director) ? movie.director.join(', ') : movie.director}
            </span>
          </div>
        )}
        {movie.actors && (
          <div className="metadata-field">
            <span className="field-label">Cast</span>
            <span className="field-value">
              {Array.isArray(movie.actors) ? movie.actors.join(', ') : movie.actors}
            </span>
          </div>
        )}
        {movie.country && (
          <div className="metadata-field">
            <span className="field-label">Country</span>
            <span className="field-value">
              {Array.isArray(movie.country) ? movie.country.join(', ') : movie.country}
            </span>
          </div>
        )}
        {movie.quality && (
          <div className="metadata-field">
            <span className="field-label">Resolution</span>
            <span className="field-value">{movie.quality}</span>
          </div>
        )}
      </div>

      {/* Recommended Titles Section */}
      {recommendations.length > 0 && (
        <div className="detail-recommendations-section">
          <h2 className="section-title">More Like This</h2>
          <div className="recommendations-grid">
            {recommendations.map((item) => (
              <div
                key={item.id}
                className="content-card"
                role="button"
                tabIndex={0}
                onClick={() => navigate(item.is_series ? `/series/${item.id}` : `/movie/${item.id}`)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    navigate(item.is_series ? `/series/${item.id}` : `/movie/${item.id}`);
                  }
                }}
              >
                <div className="card-poster-wrap">
                  <img
                    className="card-poster-img"
                    src={getPosterUrl(item.poster || item.poster_url, item.title, item.year)}
                    alt={item.title}
                    loading="lazy"
                  />
                  <div className="card-badge-top-left">
                    <span className={`badge-tag ${item.is_series ? 'series' : 'movie'}`}>
                      {item.is_series ? 'Series' : 'Movie'}
                    </span>
                  </div>
                </div>
                <div className="card-body">
                  <h4 className="card-title" title={item.title}>
                    {item.title}
                  </h4>
                  <div className="card-footer">
                    <span>{item.year || '—'}</span>
                    {item.quality && <span>{item.quality}</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

