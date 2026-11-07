import React, { useState, useEffect, useMemo, useRef } from 'react';
import { ArrowLeft, Star, Play, Check, Bookmark, Tv, AlertTriangle } from 'lucide-react';
import { MovieItem } from '../../types/catalogue';
import { getMovie } from '../../api/catalogue';
import { getSeriesSeasons } from '../player/services/playerService';
import { SeriesSeasonResponse, SeriesSeason, SeriesEpisode } from '../player/types';
import { useRouter } from '../../router';
import { useWatchlist } from '../watchlist';
import { useAuth } from '../../context/AuthContext';
import {
  resolveContinueWatchingKey,
  readContinueWatchingRecords,
} from '../continue-watching/storage';
import { ContinueWatchingRecord } from '../continue-watching/types';
import { PlaybackTarget } from '../player';
import { getPosterUrl, formatRating } from '../../utils/formatters';
import { LoadingSpinner } from '../../components/common/LoadingSpinner';

interface SeriesDetailPageProps {
  seriesId: number;
  onPlayTarget: (target: PlaybackTarget) => void;
}

export const SeriesDetailPage: React.FC<SeriesDetailPageProps> = ({ seriesId, onPlayTarget }) => {
  const { navigate, back } = useRouter();
  const { isInList, addItem, removeItem } = useWatchlist();
  const { username, role, authenticated } = useAuth();

  const [seriesItem, setSeriesItem] = useState<MovieItem | null>(null);
  const [seasonsData, setSeasonsData] = useState<SeriesSeasonResponse | null>(null);
  const [selectedSeasonNum, setSelectedSeasonNum] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isSynopsisExpanded, setIsSynopsisExpanded] = useState<boolean>(false);

  const episodesSectionRef = useRef<HTMLDivElement>(null);

  // Read Continue Watching progress
  const scopedCwKey = useMemo(() => {
    return resolveContinueWatchingKey(username, role, authenticated);
  }, [username, role, authenticated]);

  // Find most recent Continue Watching episode record for this series
  const activeContinueRecord = useMemo<ContinueWatchingRecord | null>(() => {
    const records = readContinueWatchingRecords(scopedCwKey);
    const sidStr = String(seriesId);
    return (
      records.find((r) => {
        if (r.id === seriesId || r.movie_id === seriesId) return true;
        if (typeof r.contentId === 'string' && r.contentId.includes(`series_${sidStr}_`)) {
          return true;
        }
        return false;
      }) || null
    );
  }, [seriesId, scopedCwKey]);

  // Fetch series details and season hierarchy
  useEffect(() => {
    let isCurrent = true;
    setLoading(true);
    setError(null);

    Promise.all([
      getMovie(seriesId),
      getSeriesSeasons(seriesId).catch((err) => {
        console.warn('Seasons hierarchy fetch warning:', err);
        return null;
      }),
    ])
      .then(([movieRes, seasonRes]) => {
        if (!isCurrent) return;
        setSeriesItem(movieRes);
        if (seasonRes && seasonRes.is_series && seasonRes.seasons && seasonRes.seasons.length > 0) {
          setSeasonsData(seasonRes);
          const initialS =
            activeContinueRecord?.season ||
            seasonRes.current_season ||
            seasonRes.seasons[0].season_number ||
            1;
          setSelectedSeasonNum(Number(initialS));
        }
      })
      .catch((err: any) => {
        if (!isCurrent) return;
        setError(err.message || 'Unable to retrieve series details.');
      })
      .finally(() => {
        if (isCurrent) setLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [seriesId]);

  if (loading) {
    return (
      <div className="detail-loading-container">
        <LoadingSpinner label="Loading series & seasons..." size="lg" />
      </div>
    );
  }

  if (error || !seriesItem) {
    return (
      <div className="detail-error-container">
        <div className="error-icon"><AlertTriangle size={36} strokeWidth={1.5} /></div>
        <h2 className="error-title">{error ? 'Failed to Load Series' : 'Series Not Found'}</h2>
        <p className="error-desc">
          {error || `No series was found with ID #${seriesId}. It may have been removed or updated.`}
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

  const isSaved = isInList(seriesItem.id);
  const ratingBadge = formatRating(seriesItem.rating, seriesItem.imdb);
  const isDubbed = Boolean(seriesItem.is_hindi_dubbed);
  const posterImg = getPosterUrl(
    seriesItem.poster || seriesItem.poster_url,
    seriesItem.title,
    seriesItem.year
  );

  const availableSeasons: SeriesSeason[] = seasonsData?.seasons || [];
  const currentSeasonObj = availableSeasons.find(
    (s) => Number(s.season_number) === Number(selectedSeasonNum)
  );
  const seasonEpisodes: SeriesEpisode[] = currentSeasonObj?.episodes || [];

  // Resume or Play handler
  const handlePlaySeries = () => {
    let playSeason = 1;
    let playEpisode = 1;
    let resumeTime = 0;
    let targetMovieId: number = seriesItem.id;

    if (activeContinueRecord && activeContinueRecord.season && activeContinueRecord.episode) {
      playSeason = activeContinueRecord.season;
      playEpisode = activeContinueRecord.episode;
      resumeTime = activeContinueRecord.currentTime || 0;
      if (activeContinueRecord.movie_id) {
        targetMovieId = Number(activeContinueRecord.movie_id);
      }
    } else if (availableSeasons.length > 0 && availableSeasons[0].episodes?.length) {
      const firstS = availableSeasons[0];
      playSeason = Number(firstS.season_number) || 1;
      const firstEp = firstS.episodes[0];
      playEpisode = Number(firstEp.episode_number || firstEp.e) || 1;
      if (firstEp.movie_id) targetMovieId = Number(firstEp.movie_id);
    }

    onPlayTarget({
      id: targetMovieId,
      title: seriesItem.title,
      year: seriesItem.year,
      poster: seriesItem.poster || seriesItem.poster_url,
      isSeries: true,
      season: playSeason,
      episode: playEpisode,
      source: seriesItem.source || 'yomovies',
      isHindiDubbed: isDubbed,
      resumeTime,
    });
  };

  const handleSelectSpecificEpisode = (ep: SeriesEpisode) => {
    const epNum = Number(ep.episode_number || ep.e) || 1;
    const targetMovieId = ep.movie_id ? Number(ep.movie_id) : seriesItem.id;

    // Check if this specific episode has Continue Watching record
    const records = readContinueWatchingRecords(scopedCwKey);
    const specificCw = records.find(
      (r) =>
        r.season === selectedSeasonNum &&
        r.episode === epNum &&
        (r.id === seriesItem.id || r.movie_id === targetMovieId)
    );

    onPlayTarget({
      id: targetMovieId,
      title: `${seriesItem.title} - S${String(selectedSeasonNum).padStart(2, '0')} E${String(epNum).padStart(2, '0')}`,
      year: seriesItem.year,
      poster: seriesItem.poster || seriesItem.poster_url,
      isSeries: true,
      season: selectedSeasonNum,
      episode: epNum,
      source: seriesItem.source || 'yomovies',
      isHindiDubbed: isDubbed,
      resumeTime: specificCw?.currentTime || 0,
    });
  };

  const handleToggleWatchlist = () => {
    if (isSaved) {
      removeItem(seriesItem.id);
    } else {
      addItem({
        id: seriesItem.id,
        title: seriesItem.title,
        year: seriesItem.year,
        poster: seriesItem.poster || seriesItem.poster_url || null,
        is_series: true,
        rating: seriesItem.rating,
        imdb: seriesItem.imdb,
        genres: seriesItem.genres,
        quality: seriesItem.quality,
        source: seriesItem.source,
      });
    }
  };

  const scrollToEpisodes = () => {
    episodesSectionRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const synopsisText = seriesItem.synopsis || '';
  const isSynopsisLong = synopsisText.length > 260;

  return (
    <div className="title-detail-container">
      {/* Back Navigation Bar */}
      <div className="detail-nav-bar">
        <button type="button" className="btn-nav-back" onClick={back} title="Go back to previous page">
          <ArrowLeft size={16} strokeWidth={1.5} /><span>Back</span>
        </button>
      </div>

      {/* Series Hero Section */}
      <div className="detail-hero-section">
        <div
          className="detail-hero-backdrop"
          style={{ backgroundImage: `url(${posterImg})` }}
          aria-hidden="true"
        />
        <div className="detail-hero-overlay" />

        <div className="detail-hero-content">
          <div className="detail-poster-wrap">
            <img src={posterImg} alt={seriesItem.title} className="detail-poster-img" />
          </div>

          <div className="detail-info-wrap">
            <div className="detail-badge-row">
              <span className="badge-tag series">Web Series</span>
              {isDubbed && <span className="badge-tag dubbed">Hindi Dub</span>}
              {ratingBadge && <span className="badge-tag rating"><Star size={12} strokeWidth={1.5} fill="currentColor" /> {ratingBadge}</span>}
              {availableSeasons.length > 0 && (
                <span className="badge-tag season-count">
                  {availableSeasons.length} {availableSeasons.length === 1 ? 'Season' : 'Seasons'}
                </span>
              )}
            </div>

            <h1 className="detail-title">{seriesItem.title}</h1>

            <div className="detail-meta-row">
              {seriesItem.year && <span className="meta-item">{seriesItem.year}</span>}
              {seriesItem.source && (
                <span className="meta-item meta-source">Source: {seriesItem.source.toUpperCase()}</span>
              )}
            </div>

            {/* Genre Chips */}
            {seriesItem.genres && seriesItem.genres.length > 0 && (
              <div className="detail-genre-chips">
                {seriesItem.genres.map((genre) => (
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
                onClick={handlePlaySeries}
              >
                {activeContinueRecord && activeContinueRecord.season ? (
                  <>
                    <Play size={16} strokeWidth={1.5} fill="currentColor" style={{ verticalAlign: "middle", marginRight: 6 }} /> Resume S{activeContinueRecord.season} E
                    {activeContinueRecord.episode} ({Math.round(activeContinueRecord.progressPct || 0)}%)
                  </>
                ) : (
                  <>
                    <Play size={16} strokeWidth={1.5} fill="currentColor" style={{ verticalAlign: "middle", marginRight: 6 }} /> Play Series
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

              <button
                type="button"
                className="btn btn-secondary btn-browse-episodes"
                onClick={scrollToEpisodes}
              >
                <Tv size={15} strokeWidth={1.5} /> <span>Browse Episodes</span>
              </button>
            </div>

            {/* Overview / Synopsis */}
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
                <p className="synopsis-empty">No series description available.</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Seasons & Episodes Section */}
      <div className="series-episodes-section" ref={episodesSectionRef}>
        <div className="section-header-bar">
          <h2 className="section-title">Episodes</h2>

          {/* Season Selector Tabs */}
          {availableSeasons.length > 1 && (
            <div className="season-tabs-bar">
              {availableSeasons.map((season) => {
                const sNum = Number(season.season_number);
                return (
                  <button
                    key={sNum}
                    type="button"
                    className={`season-tab-btn ${selectedSeasonNum === sNum ? 'active' : ''}`}
                    onClick={() => setSelectedSeasonNum(sNum)}
                  >
                    Season {sNum}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Episodes Grid */}
        {seasonEpisodes.length === 0 ? (
          <div className="episodes-empty-box">
            <p>No episodes currently indexed for Season {selectedSeasonNum}.</p>
          </div>
        ) : (
          <div className="episodes-list-grid">
            {seasonEpisodes.map((ep) => {
              const epNum = Number(ep.episode_number || ep.e) || 1;
              const epTitle = ep.name || `Episode ${epNum}`;
              const sPad = String(selectedSeasonNum).padStart(2, '0');
              const ePad = String(epNum).padStart(2, '0');

              // Check if episode is in Continue Watching
              const records = readContinueWatchingRecords(scopedCwKey);
              const cw = records.find(
                (r) =>
                  r.season === selectedSeasonNum &&
                  r.episode === epNum &&
                  (r.id === seriesItem.id || (ep.movie_id && r.movie_id === Number(ep.movie_id)))
              );

              return (
                <div
                  key={`${selectedSeasonNum}-${epNum}`}
                  className="episode-detail-card"
                  role="button"
                  tabIndex={0}
                  onClick={() => handleSelectSpecificEpisode(ep)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleSelectSpecificEpisode(ep);
                    }
                  }}
                  aria-label={`Season ${selectedSeasonNum} Episode ${epNum}: ${epTitle}`}
                >
                  <div className="episode-thumbnail-wrap">
                    <img
                      src={posterImg}
                      alt={epTitle}
                      className="episode-thumbnail-img"
                      loading="lazy"
                    />
                    <div className="episode-play-overlay"><Play size={16} strokeWidth={1.5} fill="currentColor" /></div>
                    {cw && cw.progressPct && (
                      <div className="episode-progress-bar-wrap">
                        <div
                          className="episode-progress-bar-fill"
                          style={{ width: `${Math.min(100, Math.max(0, cw.progressPct))}%` }}
                        />
                      </div>
                    )}
                  </div>

                  <div className="episode-card-body">
                    <div className="episode-header-line">
                      <span className="episode-code">S{sPad} E{ePad}</span>
                      <h4 className="episode-title" title={epTitle}>
                        {epTitle}
                      </h4>
                    </div>
                    {ep.overview ? (
                      <p className="episode-overview">{ep.overview}</p>
                    ) : (
                      <p className="episode-overview muted">Watch this episode of {seriesItem.title}.</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
