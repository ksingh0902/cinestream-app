import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  ArrowLeft,
  X,
  Languages,
  Tv,
  ChevronDown,
  Zap,
  Radio,
} from 'lucide-react';
import { useAuth } from '../../../context/AuthContext';
import {
  resolveContinueWatchingKey,
  getContinueWatchingRecord,
} from '../../continue-watching/storage';
import {
  PlaybackTarget,
  StreamInfo,
  StreamServer,
  SubtitleTrack,
  SeriesSeasonResponse,
} from '../types';
import {
  resolveStream,
  getSubtitleUrl,
  isPermittedIframeOrigin,
  cleanTitle,
  buildContentId,
  getSeriesSeasons,
} from '../services/playerService';
import { useHlsPlayer } from '../hooks/useHlsPlayer';
import { usePlaybackProgress } from '../hooks/usePlaybackProgress';
import { PlayerLoading } from './PlayerLoading';
import { PlayerError } from './PlayerError';

interface PlayerModalProps {
  isOpen: boolean;
  target: PlaybackTarget | null;
  onClose: () => void;
}

export const PlayerModal: React.FC<PlayerModalProps> = ({
  isOpen,
  target,
  onClose,
}) => {
  const { username, role, authenticated } = useAuth();
  const scopedKey = resolveContinueWatchingKey(username, role, authenticated);

  const overlayRef = useRef<HTMLDivElement | null>(null);
  const seasonsSectionRef = useRef<HTMLDivElement | null>(null);
  const detailsRef = useRef<HTMLDivElement | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Active playback target (updates when switching episodes without closing modal)
  const [currentTarget, setCurrentTarget] = useState<PlaybackTarget | null>(target);

  // Stream resolution & server state
  const [isResolving, setIsResolving] = useState<boolean>(true);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const [streamInfo, setStreamInfo] = useState<StreamInfo | null>(null);
  const [activeServerIndex, setActiveServerIndex] = useState<number>(0);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);

  // Watchdog & fallback telemetry refs
  const streamInfoRef = useRef<StreamInfo | null>(null);
  streamInfoRef.current = streamInfo;
  const watchdogTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const noticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptSeqRef = useRef<number>(0);
  const failedServersRef = useRef<Set<number>>(new Set());
  const playbackStartedRef = useRef<boolean>(false);
  const triggerAutoFallbackRef = useRef<(failedIdx: number, reason?: string) => void>(() => {});
  const startWatchdogRef = useRef<(serverIdx: number) => void>(() => {});

  // Series & Seasons state
  const [seriesData, setSeriesData] = useState<SeriesSeasonResponse | null>(null);
  const [selectedSeasonTab, setSelectedSeasonTab] = useState<number>(1);
  const [movieMeta, setMovieMeta] = useState<any>(null);

  const activeStreamAbortRef = useRef<AbortController | null>(null);
  const seasonsAbortRef = useRef<AbortController | null>(null);
  const isTransitioningRef = useRef<boolean>(false);

  // Sync currentTarget when target prop changes, checking Continue Watching storage for resume time
  useEffect(() => {
    if (target) {
      let resume = target.resumeTime || 0;
      if (resume <= 0) {
        const contentId = buildContentId(target);
        const record = getContinueWatchingRecord(scopedKey, contentId);
        if (record && !record.isCompleted && record.currentTime >= 5) {
          resume = record.currentTime;
        }
      }
      setCurrentTarget({
        ...target,
        resumeTime: resume,
      });
      if (target.season) {
        setSelectedSeasonTab(target.season);
      }
    } else {
      setCurrentTarget(null);
    }
  }, [target, scopedKey]);

  // Determine series flags and active numbers
  const isSeries = Boolean(
    currentTarget?.isSeries ||
    (seriesData && seriesData.is_series) ||
    (currentTarget?.title && /season|episode|s\d+\s*e\d+/i.test(currentTarget.title))
  );

  const activeSeasonNum = currentTarget?.season ?? seriesData?.current_season ?? selectedSeasonTab ?? 1;
  const activeEpisodeNum = currentTarget?.episode ?? seriesData?.current_episode ?? 1;

  // Active server info
  const activeServer: StreamServer | null =
    streamInfo && streamInfo.servers && streamInfo.servers.length > activeServerIndex
      ? streamInfo.servers[activeServerIndex]
      : null;

  const isIframe = Boolean(activeServer && activeServer.kind === 'iframe');
  const activeIframeOrigin =
    isIframe && activeServer?.url && isPermittedIframeOrigin(activeServer.url)
      ? new URL(activeServer.url, window.location.origin).origin
      : null;
  const hlsSource = !isIframe && activeServer?.url ? activeServer.url : null;

  // Subtitle track
  const subtitleTrack: SubtitleTrack | null = currentTarget
    ? {
        id: `v-sub-${currentTarget.id}`,
        label: 'English',
        src: getSubtitleUrl(currentTarget.id),
        srclang: 'en',
        default: true,
      }
    : null;

  // Clear any pending 10s playback watchdog
  const clearWatchdog = useCallback(() => {
    if (watchdogTimerRef.current) {
      clearTimeout(watchdogTimerRef.current);
      watchdogTimerRef.current = null;
    }
  }, []);

  // Automatic server fallback routine (exact production Vanilla behavior)
  const triggerAutoFallback = useCallback(
    (failedIdx: number, _errorReason?: string) => {
      clearWatchdog();
      const servers = streamInfoRef.current?.servers;
      if (!servers || servers.length <= 1) {
        if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
        setStatusNotice(null);
        setResolveError('Media unavailable across all servers for this title.');
        return;
      }

      failedServersRef.current.add(failedIdx);

      // Find next candidate server index that has not failed yet in this session
      let nextIdx = failedIdx + 1;
      while (nextIdx < servers.length && failedServersRef.current.has(nextIdx)) {
        nextIdx++;
      }

      if (nextIdx < servers.length) {
        const curSrv = servers[failedIdx];
        const nextSrv = servers[nextIdx];
        const curLabel = (curSrv?.label || `Server ${failedIdx + 1}`).replace(/\s*\(Recommended\)/, '');
        const nextLabel = (nextSrv?.label || `Server ${nextIdx + 1}`).replace(/\s*\(Recommended\)/, '');

        const notice = `${curLabel} unavailable — switching to ${nextLabel}…`;
        setStatusNotice(notice);
        console.info(`[Auto-Fallback] ${notice}`);

        playbackStartedRef.current = false;
        setActiveServerIndex(nextIdx);
        setResolveError(null);

        if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
        noticeTimerRef.current = setTimeout(() => {
          setStatusNotice(null);
        }, 3500);

        startWatchdogRef.current(nextIdx);
      } else {
        console.warn('[Auto-Fallback] All stream servers exhausted for this title.');
        if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
        setStatusNotice(null);
        setResolveError('Media unavailable across all servers for this title.');
      }
    },
    [clearWatchdog]
  );
  triggerAutoFallbackRef.current = triggerAutoFallback;

  // Playback watchdog (timer auto-switch disabled to prevent disrupting working streams)
  const startWatchdog = useCallback(
    (_serverIdx: number) => {
      clearWatchdog();
      // Notice: Do NOT automatically switch servers on a timeout.
      // Third-party iframes (DooFlix, Ask4Movies, etc.) do not report cross-origin
      // telemetry, which previously caused working streams to be abandoned every 10s.
    },
    [clearWatchdog]
  );
  startWatchdogRef.current = startWatchdog;

  // Playback verified callback (clears watchdog as soon as genuine video/telemetry starts)
  const handlePlaybackStarted = useCallback(() => {
    playbackStartedRef.current = true;
    clearWatchdog();
    if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
    setStatusNotice(null);
  }, [clearWatchdog]);

  // Continue Watching & Telemetry Hook
  const { flushProgress } = usePlaybackProgress({
    target: currentTarget,
    videoRef,
    iframeRef,
    isIframe,
    activeIframeOrigin,
    streamSrc: hlsSource,
    isResolving,
    onPlaybackStarted: handlePlaybackStarted,
  });

  const flushProgressRef = useRef<() => void>(flushProgress);
  flushProgressRef.current = flushProgress;

  // Fetch Series Seasons Tree
  const fetchSeasonsHierarchy = useCallback(
    async (movieId: number | string) => {
      if (seasonsAbortRef.current) {
        seasonsAbortRef.current.abort();
      }
      seasonsAbortRef.current = new AbortController();

      try {
        const data = await getSeriesSeasons(movieId, seasonsAbortRef.current.signal);
        if (data.is_series && data.seasons && data.seasons.length > 0) {
          setSeriesData(data);
          if (data.current_season) {
            setSelectedSeasonTab(data.current_season);
          }
        }
      } catch (err: any) {
        if (err.name === 'AbortError') return;
        console.warn('Series seasons load failed:', err);
      }
    },
    []
  );

  // Episode transition handler (updates target and triggers stream resolve)
  const handleSelectEpisode = useCallback(
    (seasonNum: number, episodeNum: number, epMovieId?: number | string | null) => {
      if (!currentTarget) return;
      if (isTransitioningRef.current) return;
      isTransitioningRef.current = true;
      window.setTimeout(() => {
        isTransitioningRef.current = false;
      }, 500);

      // Force save outgoing episode progress
      flushProgressRef.current();

      // Reset watchdog & server tracking for new episode
      clearWatchdog();
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
      setStatusNotice(null);
      attemptSeqRef.current += 1;
      failedServersRef.current.clear();
      playbackStartedRef.current = false;

      const targetMovieId = epMovieId ? Number(epMovieId) : currentTarget.id;

      // Look up existing resume progress for the new episode if available
      const contentId = buildContentId({
        ...currentTarget,
        id: targetMovieId,
        isSeries: true,
        canonicalSeriesId: currentTarget.canonicalSeriesId || String(currentTarget.id),
        season: seasonNum,
        episode: episodeNum,
      });
      const savedRecord = getContinueWatchingRecord(scopedKey, contentId);
      const resumeTime =
        savedRecord && !savedRecord.isCompleted && savedRecord.currentTime >= 5
          ? savedRecord.currentTime
          : 0;

      setCurrentTarget((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          id: targetMovieId,
          season: seasonNum,
          episode: episodeNum,
          resumeTime,
        };
      });

      setSelectedSeasonTab(seasonNum);
    },
    [currentTarget, scopedKey, clearWatchdog]
  );

  // Fetch stream data from backend
  const fetchStreamData = useCallback(
    async (fresh: boolean = false) => {
      if (!currentTarget) return;

      if (activeStreamAbortRef.current) {
        activeStreamAbortRef.current.abort();
      }
      activeStreamAbortRef.current = new AbortController();

      setIsResolving(true);
      setResolveError(null);
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
      setStatusNotice(null);

      try {
        const info = await resolveStream(currentTarget.id, {
          fresh,
          season: currentTarget.season,
          episode: currentTarget.episode,
          signal: activeStreamAbortRef.current.signal,
        });

        attemptSeqRef.current += 1;
        failedServersRef.current.clear();
        playbackStartedRef.current = false;
        setStatusNotice(null);
        setResolveError(null);
        streamInfoRef.current = info;
        setStreamInfo(info);
        setActiveServerIndex(0);

        if (info.servers && info.servers.length > 0) {
          startWatchdogRef.current(0);
        }
      } catch (err: any) {
        if (err.name === 'AbortError') return;
        setResolveError(err.message || 'Stream unavailable. Please try again or switch server.');
      } finally {
        setIsResolving(false);
      }
    },
    [currentTarget]
  );

  // Resolve stream when opened or currentTarget changes
  useEffect(() => {
    if (!isOpen || !currentTarget) {
      setStreamInfo(null);
      setIsResolving(false);
      setResolveError(null);
      return;
    }

    fetchStreamData(false);

    // Fetch rich metadata (synopsis, rating, genres) if not provided
    fetch(`/api/movie/${currentTarget.id}`, { credentials: 'include' })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setMovieMeta(data);
      })
      .catch(() => {});

    if (isSeries || currentTarget.isSeries) {
      fetchSeasonsHierarchy(currentTarget.id);
    }

    return () => {
      clearWatchdog();
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
      if (activeStreamAbortRef.current) {
        activeStreamAbortRef.current.abort();
      }
      if (seasonsAbortRef.current) {
        seasonsAbortRef.current.abort();
      }
    };
  }, [isOpen, currentTarget, isSeries, fetchStreamData, fetchSeasonsHierarchy, clearWatchdog]);

  // Self-heal callback (called on expired stream token or HLS 401/403)
  const handleSelfHeal = useCallback(() => {
    console.info('Triggering self-healing stream refresh...');
    fetchStreamData(true);
  }, [fetchStreamData]);

  // Hls.js hook for native HLS streams with auto-fallback on fatal/404 errors
  useHlsPlayer({
    videoRef,
    src: hlsSource,
    autoPlay: true,
    initialSeekTime: currentTarget?.resumeTime || 0,
    onSelfHeal: handleSelfHeal,
    onFatalError: (msg) => {
      console.warn('HLS stream fatal/resource error caught in PlayerModal:', msg);
      triggerAutoFallbackRef.current(activeServerIndex, msg);
    },
  });

  // Close player handler
  const handleClose = useCallback(() => {
    clearWatchdog();
    if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
    setStatusNotice(null);
    flushProgress();
    onClose();
  }, [clearWatchdog, flushProgress, onClose]);

  // Server switch handler (resets watchdog timer for selected server)
  const handleSelectServer = useCallback(
    (index: number) => {
      flushProgress();
      clearWatchdog();
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
      setStatusNotice(null);
      setResolveError(null);
      failedServersRef.current.delete(index);
      playbackStartedRef.current = false;
      setActiveServerIndex(index);
      startWatchdogRef.current(index);
    },
    [flushProgress, clearWatchdog]
  );

  // Scroll smoothly down to the series episodes section
  const scrollToEpisodes = useCallback(() => {
    if (seasonsSectionRef.current) {
      seasonsSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, []);

  // Global keydown listener: TV Back/Escape support (preserves TV browser spatial navigation)
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      // 1. Escape key / TV Back support (Tizen/WebOS: 10009, 'Back', 'GoBack')
      if (
        e.key === 'Escape' ||
        e.key === 'GoBack' ||
        e.key === 'Back' ||
        (e as any).keyCode === 10009
      ) {
        if (document.fullscreenElement) {
          // Allow browser to exit native fullscreen naturally
          return;
        }
        e.preventDefault();
        handleClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, handleClose]);

  // Lock root document scroll when watch overlay is open (eliminates double scroll)
  useEffect(() => {
    if (isOpen) {
      document.documentElement.classList.add('watch-page');
      document.body.classList.add('watch-page');
    } else {
      document.documentElement.classList.remove('watch-page');
      document.body.classList.remove('watch-page');
    }
    return () => {
      document.documentElement.classList.remove('watch-page');
      document.body.classList.remove('watch-page');
    };
  }, [isOpen]);

  if (!isOpen || !currentTarget) return null;

  const baseTitle = cleanTitle(seriesData?.title || currentTarget.title);
  const epSuffix = isSeries
    ? ` · S${String(activeSeasonNum).padStart(2, '0')} E${String(activeEpisodeNum).padStart(2, '0')}`
    : '';
  const yr = currentTarget.year ? ` (${currentTarget.year})` : '';

  const activeSeasonData = seriesData?.seasons?.find(
    (s) => Number(s.season_number) === Number(selectedSeasonTab)
  ) || seriesData?.seasons?.[0];

  const hasSeasons = Boolean(seriesData?.seasons && seriesData.seasons.length > 0);

  const getSourceBadge = (source?: string) => {
    if (!source) return null;
    const s = source.toLowerCase();
    if (s.includes('ask')) return <span className="src-badge ask">🍿 ASK</span>;
    if (s.includes('doo')) return <span className="src-badge doo">▶️ DOO</span>;
    if (s.includes('movie7') || s.includes('m7')) return <span className="src-badge m7">⚡ 7</span>;
    return <span className="src-badge ym">🎬 YM</span>;
  };

  return (
    <div
      className="prod-player-overlay"
      ref={overlayRef}
      tabIndex={-1}
      style={{ outline: 'none' }}
    >
      <div className="prod-player-box">
        {/* 1. Top Navigation Bar — In normal document flow above player */}
        <div className="watch-nav">
          <button
            type="button"
            className="btn-watch-back"
            onClick={handleClose}
            title="Back to Home (Escape)"
          >
            <ArrowLeft size={16} strokeWidth={2} />
            <span>Back to Home</span>
          </button>

          <div className="watch-nav-right">
            {isSeries && hasSeasons ? (
              <button
                type="button"
                className="btn-scroll-episodes"
                onClick={scrollToEpisodes}
                title="Jump down to Episodes & Seasons"
              >
                <Tv size={14} strokeWidth={1.5} />
                <span>Episodes & Seasons</span>
                <ChevronDown size={14} strokeWidth={1.5} />
              </button>
            ) : (
              <button
                type="button"
                className="btn-scroll-details"
                onClick={() => {
                  detailsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }}
                title="Jump down to Movie Details"
              >
                <ChevronDown size={14} strokeWidth={1.5} />
                <span>Details</span>
              </button>
            )}
            <button
              type="button"
              className="btn-close"
              onClick={handleClose}
              title="Close Player (Escape)"
            >
              <X size={15} strokeWidth={2} />
              <span>Close</span>
            </button>
          </div>
        </div>

        {/* 2. Title Row — In normal document flow above player */}
        <div className="prod-player-title-row">
          <h2 className="prod-player-title" title={`${baseTitle}${epSuffix}${yr}`}>
            {getSourceBadge(currentTarget.source)}
            {currentTarget.isHindiDubbed && (
              <span className="dub-badge">
                <Languages size={12} strokeWidth={1.5} />
                <span>Hindi Dubbed</span>
              </span>
            )}
            <span className="title-text">
              {baseTitle}
              {epSuffix}
              {yr}
            </span>
          </h2>
        </div>

        {/* 3. Server Selector — In normal document flow above player container */}
        {streamInfo && streamInfo.servers && streamInfo.servers.length > 1 && (
          <div id="server-switcher" className="prod-server-switcher">
            <span className="srv-label">Servers:</span>
            <div className="srv-pills">
              {streamInfo.servers.map((srv, idx) => {
                const isActive = idx === activeServerIndex;
                const isHls = srv.kind === 'hls';
                return (
                  <button
                    key={`${srv.url}-${idx}`}
                    type="button"
                    className={`pill ${isActive ? 'active' : ''}`}
                    onClick={() => handleSelectServer(idx)}
                    title={`Switch to ${srv.label}`}
                  >
                    {isHls ? (
                      <Radio size={13} strokeWidth={1.5} />
                    ) : (
                      <Zap size={13} strokeWidth={1.5} />
                    )}
                    <span>{srv.label || `Server ${idx + 1}`}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* 4. Player Container — 16:9 Aspect Ratio, Maximum Width 1040px */}
        <div
          className="player-container"
          id="player-container"
          tabIndex={0}
          role="region"
          aria-label="Video Player"
          onKeyDown={(e) => {
            if (e.key === 'Enter' || (e as any).keyCode === 13) {
              if (isIframe && iframeRef.current) {
                iframeRef.current.focus();
              } else if (videoRef.current) {
                videoRef.current.focus();
                if (videoRef.current.paused) {
                  videoRef.current.play().catch(() => {});
                } else {
                  videoRef.current.pause();
                }
              }
            }
          }}
        >
          {/* HTML5 Native Video for HLS Streams */}
          <video
            ref={videoRef}
            id="v"
            tabIndex={0}
            controls
            playsInline
            controlsList="noremoteplayback"
            crossOrigin="anonymous"
            style={{
              display: isIframe ? 'none' : 'block',
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              background: '#000',
            }}
          >
            {subtitleTrack && (
              <track
                id={subtitleTrack.id}
                kind="subtitles"
                label={subtitleTrack.label}
                srcLang={subtitleTrack.srclang}
                src={subtitleTrack.src}
                default={subtitleTrack.default}
              />
            )}
          </video>

          {/* Embed Iframe for Third-Party Servers (Exact Production Markup & Permissions Policy) */}
          <iframe
            ref={iframeRef}
            id="p-iframe"
            tabIndex={0}
            key={isIframe ? (activeServer?.url || `iframe-srv-${activeServerIndex}`) : 'iframe-hidden'}
            src={isIframe && activeServer?.url ? activeServer.url : undefined}
            style={{
              display: isIframe ? 'block' : 'none',
              width: '100%',
              height: '100%',
              border: 0,
              position: 'absolute',
              inset: 0,
            }}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share; fullscreen"
            allowFullScreen={true}
            // @ts-ignore
            webkitallowfullscreen="true"
            // @ts-ignore
            mozallowfullscreen="true"
            referrerPolicy="origin"
            title="Video Player Stream"
          />

          {/* Resolving Stream Loading State */}
          {isResolving && (
            <PlayerLoading
              label={
                isSeries
                  ? `Loading Season ${activeSeasonNum} Episode ${activeEpisodeNum}…`
                  : 'Resolving stream from high-speed servers…'
              }
            />
          )}

          {/* Stream Error State */}
          {resolveError && !isResolving && (
            <PlayerError
              message={resolveError}
              onRetry={() => {
                failedServersRef.current.clear();
                setActiveServerIndex(0);
                fetchStreamData(true);
              }}
              onSwitchServer={
                streamInfo && streamInfo.servers.length > 1
                  ? () =>
                      handleSelectServer(
                        (activeServerIndex + 1) % streamInfo.servers.length
                      )
                  : undefined
              }
              hasAlternateServers={Boolean(
                streamInfo && streamInfo.servers.length > 1
              )}
            />
          )}
        </div>

        {/* 5. Stream Status Line */}
        <div className="prod-player-status">
          <span>
            {statusNotice && !resolveError ? (
              <span className="status-notice-text">
                <span className="spinner-inline"></span> {statusNotice}
              </span>
            ) : (
              <>
                {activeServer?.label || `Server ${activeServerIndex + 1}`}
                {epSuffix} · Active stream player
              </>
            )}
          </span>
        </div>

        {/* TV Remote & Touch Scroll Cue (Navigates down to episodes or details on D-pad) */}
        <button
          type="button"
          className="player-scroll-hint"
          onClick={() => {
            if (seasonsSectionRef.current) {
              seasonsSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
            } else if (detailsRef.current) {
              detailsRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
            } else {
              overlayRef.current?.scrollBy({ top: 350, behavior: 'smooth' });
            }
          }}
          aria-label={isSeries && hasSeasons ? 'Jump down to episodes' : 'Scroll down for details'}
        >
          <ChevronDown size={14} strokeWidth={2} />
          <span>{isSeries && hasSeasons ? 'View Episodes & Seasons' : 'Scroll down for Details'}</span>
          <ChevronDown size={14} strokeWidth={2} />
        </button>

        {/* 6. Series Seasons & Episodes Grid — In normal document flow below player */}
        {isSeries && hasSeasons && (
          <div
            id="series-seasons-wrap"
            className="series-seasons-wrap"
            ref={seasonsSectionRef}
          >
            <div className="seasons-top-bar">
              <div className="seasons-title">
                <Tv size={16} strokeWidth={1.5} />
                <span>{seriesData?.title || 'Episodes'}</span>
                <span className="seasons-count-badge">
                  {activeSeasonData?.episode_count || activeSeasonData?.episodes?.length || 0} Episodes
                </span>
              </div>
            </div>

            {/* Season Tabs */}
            {seriesData?.seasons && seriesData.seasons.length > 1 && (
              <div className="seasons-nav" role="tablist" aria-label="Series Seasons">
                {seriesData.seasons.map((s) => {
                  const sNum = Number(s.season_number);
                  const isTabActive = sNum === Number(selectedSeasonTab);
                  return (
                    <button
                      key={`season-tab-${sNum}`}
                      type="button"
                      className={`season-tab-btn ${isTabActive ? 'active' : ''}`}
                      onClick={() => setSelectedSeasonTab(sNum)}
                      role="tab"
                      aria-selected={isTabActive}
                    >
                      {s.name || `Season ${sNum}`} ({s.episode_count || s.episodes?.length || 0})
                    </button>
                  );
                })}
              </div>
            )}

            {/* Episode Chips Grid */}
            <div className="episodes-grid" role="list" aria-label="Season Episodes">
              {activeSeasonData?.episodes?.map((ep) => {
                const epNum = ep.episode_number ?? ep.e;
                const isEpActive =
                  ep.s === activeSeasonNum && epNum === activeEpisodeNum;
                const label = `Ep ${epNum}`;
                const fullTitle = `${ep.name || label}${ep.movie_id && ep.movie_id !== currentTarget.id ? ' (Native)' : ''}`;

                return (
                  <button
                    key={`ep-chip-${ep.s}-${epNum}`}
                    type="button"
                    className={`ep-chip ${isEpActive ? 'active' : ''}`}
                    title={fullTitle}
                    onClick={() => handleSelectEpisode(ep.s, epNum, ep.movie_id)}
                    role="listitem"
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* 7. Details / Synopsis Section — In normal document flow below episodes */}
        <div
          className="watch-details"
          ref={detailsRef}
          tabIndex={0}
          onFocus={(e) => {
            e.currentTarget.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }}
        >
          <div className="watch-meta">
            {(movieMeta?.rating || currentTarget.rating) && (
              <span>Rating {movieMeta?.rating || currentTarget.rating}</span>
            )}
            {(movieMeta?.year || currentTarget.year) && (
              <span>{movieMeta?.year || currentTarget.year}</span>
            )}
            {(movieMeta?.duration_s || currentTarget.duration_s) && (
              <span>
                {Math.max(
                  1,
                  Math.round(
                    Number(movieMeta?.duration_s || currentTarget.duration_s) / 60
                  )
                )}{' '}
                min
              </span>
            )}
            {(movieMeta?.quality || currentTarget.quality) && (
              <span>{movieMeta?.quality || currentTarget.quality}</span>
            )}
            {(movieMeta?.genres || currentTarget.genres) && (
              <span>
                {Array.isArray(movieMeta?.genres || currentTarget.genres)
                  ? (movieMeta?.genres || currentTarget.genres).join(', ')
                  : (movieMeta?.genres || currentTarget.genres)}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
