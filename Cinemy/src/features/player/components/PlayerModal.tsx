import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../../../context/AuthContext';
import {
  resolveContinueWatchingKey,
  getContinueWatchingRecord,
  readContinueWatchingRecords,
  saveContinueWatchingRecord,
  removeContinueWatchingRecord,
} from '../../continue-watching/storage';
import { ContinueWatchingRecord } from '../../continue-watching/types';
import {
  PlaybackTarget,
  StreamInfo,
  StreamServer,
  SubtitleTrack,
  SeriesSeasonResponse,
  NextEpisodeInfo,
} from '../types';
import {
  resolveStream,
  getSubtitleUrl,
  isPermittedIframeOrigin,
  cleanTitle,
  buildContentId,
  getSeriesSeasons,
  getNextEpisodeInfo,
} from '../services/playerService';
import { useHlsPlayer } from '../hooks/useHlsPlayer';
import { usePlaybackProgress } from '../hooks/usePlaybackProgress';

interface PlayerModalProps {
  isOpen: boolean;
  target: PlaybackTarget | null;
  onClose: () => void;
}

function formatTime(sec: number): string {
  if (isNaN(sec) || sec < 0) return '0:00';
  const total = Math.floor(sec);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${h}:${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
  }
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

function isBackOrExitKey(e: KeyboardEvent): boolean {
  const k = e.key;
  const c = (e as any).keyCode || (e as any).which;
  if (
    k === 'Escape' ||
    k === 'Back' ||
    k === 'BrowserBack' ||
    k === 'GoBack' ||
    k === 'Exit' ||
    k === 'Return' ||
    k === 'Cancel' ||
    k === 'Uprev'
  ) {
    return true;
  }
  // 27: Escape, 4: Android Back, 461: LG webOS Back, 10009: Samsung Tizen Return, 10182: Samsung Tizen Exit, 166: Browser Back
  if (c === 27 || c === 4 || c === 461 || c === 10009 || c === 10182 || c === 166) {
    return true;
  }
  const tag = document.activeElement ? document.activeElement.tagName : '';
  if ((k === 'Backspace' || c === 8) && tag !== 'INPUT' && tag !== 'TEXTAREA') {
    return true;
  }
  return false;
}

export const PlayerModal: React.FC<PlayerModalProps> = ({
  isOpen,
  target,
  onClose,
}) => {
  const { username, role, authenticated } = useAuth();
  const scopedKey = resolveContinueWatchingKey(username, role, authenticated);
  const scopedKeyRef = useRef(scopedKey);
  scopedKeyRef.current = scopedKey;

  const overlayRef = useRef<HTMLDivElement | null>(null);
  const playerContainerRef = useRef<HTMLDivElement | null>(null);
  const seasonsSectionRef = useRef<HTMLDivElement | null>(null);
  const detailsRef = useRef<HTMLDivElement | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const nextEpDialogRef = useRef<HTMLDialogElement | null>(null);

  // Active playback target (updates when switching episodes or alternate editions without closing modal)
  const [currentTarget, setCurrentTarget] = useState<PlaybackTarget | null>(target);
  const lastSyncedTargetKeyRef = useRef<string | null>(null);
  const homeScrollYRef = useRef<number>(0);

  // Stream resolution & server state
  const [isResolving, setIsResolving] = useState<boolean>(false);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const [streamInfo, setStreamInfo] = useState<StreamInfo | null>(null);
  const [activeServerIndex, setActiveServerIndex] = useState<number>(0);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);
  const [showRetryBtn, setShowRetryBtn] = useState<boolean>(false);

  // HUD & Subtitle state
  const [hudText, setHudText] = useState<string>('');
  const [hudVisible, setHudVisible] = useState<boolean>(false);
  const [ccEnabled, setCcEnabled] = useState<boolean>(true);
  const hudTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Skip 10s accumulator state (Vanilla L2580-2581, L4161-4223)
  const skipAccumulatorRef = useRef<number>(0);
  const skipResetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isActivelyPlayingRef = useRef<boolean>(false);
  const isSeekingActiveRef = useRef<boolean>(false);
  const seekTargetTimeRef = useRef<number | null>(null);
  const targetSeekTimeRef = useRef<number>(0);
  const keepTimeRef = useRef<number>(0);
  const lastKnownPlayTimeRef = useRef<number>(0);

  // Resume Banner & Iframe Seek state (Vanilla L3375-3562)
  const [resumeBannerRecord, setResumeBannerRecord] = useState<ContinueWatchingRecord | null>(null);
  const iframeSeekRetryTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pendingIframeSeekTimeRef = useRef<number>(0);

  // Next Episode Overlay Popup state (Vanilla L3668-3727, L4610-4760)
  const [nextEpPopup, setNextEpPopup] = useState<NextEpisodeInfo | null>(null);
  const [isNextEpLoading, setIsNextEpLoading] = useState<boolean>(false);
  const shownNextEpPopupKeyRef = useRef<string>('');
  const dismissedNextEpPopupKeyRef = useRef<string>('');
  const isNextEpTransitioningRef = useRef<boolean>(false);

  // Fullscreen & Episode Fullscreen Preservation state (Vanilla L4689-4737, L5434-5602)
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [, setIsVideoPlaying] = useState<boolean>(false);
  const lastIframeSrcRef = useRef<string>('about:blank');
  const isPreservingEpisodeFsRef = useRef<boolean>(false);
  const episodeFsPreserveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fsActivityTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Scroll Episodes Button state (Vanilla L4840-4873)
  const [isScrolledPastEpisodes, setIsScrolledPastEpisodes] = useState<boolean>(false);

  // Watchdog & fallback telemetry refs
  const streamInfoRef = useRef<StreamInfo | null>(null);
  streamInfoRef.current = streamInfo;
  const watchdogTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const noticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const slowNoticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timeoutNoticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resolveSeqRef = useRef<number>(0);
  const attemptSeqRef = useRef<number>(0);
  const failedServersRef = useRef<Set<number>>(new Set());
  const playbackStartedRef = useRef<boolean>(false);
  const triggerAutoFallbackRef = useRef<(failedIdx: number, reason?: string) => void>(() => {});
  const startWatchdogRef = useRef<(serverIdx: number) => void>(() => {});

  // Series & Seasons state
  const [seriesData, setSeriesData] = useState<SeriesSeasonResponse | null>(null);
  const seriesDataRef = useRef<SeriesSeasonResponse | null>(null);
  seriesDataRef.current = seriesData;
  const [selectedSeasonTab, setSelectedSeasonTab] = useState<number>(1);
  const [movieMeta, setMovieMeta] = useState<any>(null);

  const activeStreamAbortRef = useRef<AbortController | null>(null);
  const seasonsAbortRef = useRef<AbortController | null>(null);
  const isTransitioningRef = useRef<boolean>(false);

  // HUD helper (Vanilla L4152-4158)
  const showHud = useCallback((text: string) => {
    setHudText(text);
    setHudVisible(true);
    if (hudTimerRef.current) clearTimeout(hudTimerRef.current);
    hudTimerRef.current = setTimeout(() => {
      setHudVisible(false);
    }, 850);
  }, []);

  // Register Samsung Tizen TV remote Back & Exit keys once (Vanilla L5408-5414)
  useEffect(() => {
    try {
      const w = window as any;
      if (w.tizen && w.tizen.tvinputdevice) {
        ['Return', 'Exit'].forEach((k) => {
          try {
            w.tizen.tvinputdevice.registerKey(k);
          } catch {}
        });
      }
    } catch {}
  }, []);

  // Sync currentTarget when target prop changes or modal opens (Vanilla L4363-4423)
  useEffect(() => {
    if (!isOpen || !target) {
      lastSyncedTargetKeyRef.current = null;
      setCurrentTarget(null);
      return;
    }

    const targetKey = `${target.id}:${target.season ?? ''}:${target.episode ?? ''}`;
    if (lastSyncedTargetKeyRef.current === targetKey) {
      return;
    }
    lastSyncedTargetKeyRef.current = targetKey;

    let resolvedSeason = target.season;
    let resolvedEpisode = target.episode;
    const isTargetSeries = Boolean(
      target.isSeries || (target.title && /season|episode|\bs\d+\s*e\d+\b/i.test(target.title))
    );

    // Vanilla L4395-4413: If opening series without explicit targetSeason/targetEpisode, restore active episode from Continue Watching
    if (isTargetSeries && resolvedSeason == null && resolvedEpisode == null) {
      const allCw = readContinueWatchingRecords(scopedKeyRef.current);
      const canonInitId = String(target.canonicalSeriesId || target.id);
      const seriesEps = allCw.filter((it) => {
        const isSer = Boolean(it.is_series || (it.contentId && it.contentId.startsWith('series_')));
        if (!isSer) return false;
        const sMatch = it.contentId ? it.contentId.match(/^series_(.+)_s\d+_e\d+$/) : null;
        const sId = String(it.series_id || (sMatch ? sMatch[1] : null) || it.id || '');
        return sId === canonInitId || sId === String(target.id) || String(it.id) === String(target.id);
      });
      if (seriesEps.length > 0) {
        seriesEps.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
        const activeSavedEp = seriesEps.find((ep) => !ep.isCompleted) || seriesEps[0];
        if (activeSavedEp && activeSavedEp.season != null && activeSavedEp.episode != null) {
          resolvedSeason = activeSavedEp.season;
          resolvedEpisode = activeSavedEp.episode;
        }
      }
    }

    const normalizedTarget: PlaybackTarget = {
      ...target,
      isSeries: isTargetSeries,
      season: isTargetSeries ? (resolvedSeason ?? 1) : undefined,
      episode: isTargetSeries ? (resolvedEpisode ?? 1) : undefined,
    };

    let resume = target.resumeTime || 0;
    if (resume <= 0) {
      const contentId = buildContentId(normalizedTarget);
      const record = getContinueWatchingRecord(scopedKeyRef.current, contentId);
      if (record && !record.isCompleted && record.currentTime >= 5) {
        resume = record.currentTime;
      }
    }

    setSeriesData(null);
    setMovieMeta(null);
    setNextEpPopup(null);
    shownNextEpPopupKeyRef.current = '';
    dismissedNextEpPopupKeyRef.current = '';
    setCurrentTarget({
      ...normalizedTarget,
      resumeTime: resume,
    });
    if (normalizedTarget.season) {
      setSelectedSeasonTab(normalizedTarget.season);
    }
  }, [isOpen, target]);

  // Determine series flags and active numbers
  const isSeries = Boolean(
    currentTarget?.isSeries ||
      (seriesData && seriesData.is_series) ||
      (currentTarget?.title && /season|episode|\bs\d+\s*e\d+\b/i.test(currentTarget.title))
  );

  const activeSeasonNum = currentTarget?.season ?? seriesData?.current_season ?? selectedSeasonTab ?? 1;
  const activeEpisodeNum = currentTarget?.episode ?? seriesData?.current_episode ?? 1;

  // Active server info
  const activeServer: StreamServer | null =
    streamInfo && streamInfo.servers && streamInfo.servers.length > activeServerIndex
      ? streamInfo.servers[activeServerIndex]
      : null;

  const isIframe = Boolean(activeServer && activeServer.kind === 'iframe');
  const isNativeVideo = Boolean(activeServer && activeServer.kind !== 'iframe');
  const activeIframeOrigin =
    isIframe && activeServer?.url && isPermittedIframeOrigin(activeServer.url)
      ? new URL(activeServer.url, window.location.origin).origin
      : null;
  const hlsSource = isNativeVideo && activeServer?.url ? activeServer.url : null;

  // Subtitle track
  const subtitleTrack: SubtitleTrack | null = currentTarget
    ? {
        id: 'v-sub',
        label: 'English',
        src: getSubtitleUrl(currentTarget.id),
        srclang: 'en',
        default: true,
      }
    : null;

  // Vanilla setIframeSrc(url) (L4326-4361): persistent iframe navigation without history pollution
  const setIframeSrc = useCallback((url: string) => {
    const pIframe = iframeRef.current;
    if (!pIframe) return;
    if (lastIframeSrcRef.current === url && url !== 'about:blank') {
      return;
    }
    lastIframeSrcRef.current = url;
    try {
      pIframe.src = url;
      if (pIframe.contentWindow && pIframe.contentWindow.location) {
        pIframe.contentWindow.location.replace(url);
      }
    } catch {
      pIframe.src = url;
    }
  }, []);

  // Sync persistent iframe src & visibility when activeServer or isOpen changes (Vanilla L5036-5065)
  useEffect(() => {
    const pIframe = iframeRef.current;
    const video = videoRef.current;
    if (!isOpen || !currentTarget) {
      if (pIframe) {
        pIframe.style.display = 'none';
        setIframeSrc('about:blank');
      }
      return;
    }

    if (isIframe && activeServer?.url) {
      if (video) {
        video.pause();
        video.style.display = 'none';
      }
      if (pIframe) {
        pIframe.style.display = 'block';
        setIframeSrc(activeServer.url);
      }
    } else if (isNativeVideo) {
      if (pIframe) {
        pIframe.style.display = 'none';
        setIframeSrc('about:blank');
      }
      if (video) {
        video.style.display = 'block';
      }
    } else {
      // While resolving before activeServer is set
      if (pIframe && !isPreservingEpisodeFsRef.current) {
        pIframe.style.display = 'none';
        setIframeSrc('about:blank');
      }
      if (video) {
        video.style.display = 'none';
      }
    }
  }, [isOpen, Boolean(currentTarget), isIframe, isNativeVideo, activeServer?.url, setIframeSrc]);

  // Iframe postMessage seek helpers (Vanilla L3423-3465)
  const sendIframeSeek = useCallback((sec: number) => {
    const pIframe = iframeRef.current;
    if (!pIframe || !pIframe.contentWindow) return;
    const s = Math.floor(sec);
    const messages = [
      { player: true, action: 'seek' + s },
      { player: true, action: 'play' },
      { player: true, action: 'seek', time: s, seconds: s },
      { type: 'seek', time: s, seconds: s },
      { event: 'seek', time: s, seconds: s },
      { action: 'seek', time: s, seconds: s },
      { method: 'setCurrentTime', value: s },
      { player_action: 'seek', time: s },
      { type: 'player:seek', time: s },
      { event: 'command', func: 'seekTo', args: [s, true] },
    ];
    for (const msg of messages) {
      try {
        pIframe.contentWindow.postMessage(msg, '*');
        pIframe.contentWindow.postMessage(JSON.stringify(msg), '*');
      } catch {}
    }
  }, []);

  const startIframeSeekRetry = useCallback(
    (dest: number) => {
      if (iframeSeekRetryTimerRef.current) {
        clearInterval(iframeSeekRetryTimerRef.current);
        iframeSeekRetryTimerRef.current = null;
      }
      pendingIframeSeekTimeRef.current = dest;
      sendIframeSeek(dest);

      let attempts = 0;
      iframeSeekRetryTimerRef.current = setInterval(() => {
        attempts++;
        if (attempts >= 10 || pendingIframeSeekTimeRef.current <= 0) {
          if (iframeSeekRetryTimerRef.current) {
            clearInterval(iframeSeekRetryTimerRef.current);
            iframeSeekRetryTimerRef.current = null;
          }
          pendingIframeSeekTimeRef.current = 0;
          return;
        }
        sendIframeSeek(dest);
      }, 300);
    },
    [sendIframeSeek]
  );

  // Resume Banner Evaluation (Vanilla L3375-3418)
  const evaluateResumeBanner = useCallback(
    (targetObj: PlaybackTarget | null, srv: StreamServer | null) => {
      if (!targetObj || !srv) {
        setResumeBannerRecord(null);
        return;
      }
      const uLow = (srv.url || '').toLowerCase();
      const lblLow = (srv.label || '').toLowerCase();

      // Vanilla L3379-3396: On FilmU server - do NOT show Resume or Start Over. Keep it for VIP-no-ads and native HLS.
      const isFilmU =
        uLow.includes('filmu') ||
        lblLow.includes('filmu') ||
        uLow.includes('vidly.pro') ||
        lblLow.includes('vidly');
      if (isFilmU) {
        setResumeBannerRecord(null);
        return;
      }

      const isVip = uLow.includes('vidsrc.si') || lblLow.includes('vip');
      const srvIsIframe = srv.kind === 'iframe';
      if (srvIsIframe && !isVip) {
        setResumeBannerRecord(null);
        return;
      }

      const contentId = buildContentId(targetObj);
      const saved = getContinueWatchingRecord(scopedKeyRef.current, contentId);
      const savedIsSeries = Boolean(saved?.is_series || contentId.startsWith('series_'));
      if (savedIsSeries && !isVip) {
        setResumeBannerRecord(null);
        return;
      }

      const isEligible = Boolean(
        saved &&
          saved.currentTime >= 5 &&
          (savedIsSeries
            ? !saved.isCompleted
            : !saved.duration || saved.currentTime / saved.duration < 0.95)
      );
      if (isEligible && saved) {
        setResumeBannerRecord(saved);
      } else {
        setResumeBannerRecord(null);
      }
    },
    []
  );

  useEffect(() => {
    evaluateResumeBanner(currentTarget, activeServer);
  }, [currentTarget, activeServer, evaluateResumeBanner]);

  const confirmResumePlayback = useCallback(() => {
    if (!resumeBannerRecord || !resumeBannerRecord.currentTime) {
      setResumeBannerRecord(null);
      return;
    }
    const dest = resumeBannerRecord.currentTime;
    setResumeBannerRecord(null);
    targetSeekTimeRef.current = dest;

    if (isIframe) {
      startIframeSeekRetry(dest);
      showHud('Resumed from ' + formatTime(dest));
      targetSeekTimeRef.current = 0;
    } else if (videoRef.current) {
      const video = videoRef.current;
      try {
        const clamped =
          video.duration && !isNaN(video.duration) && video.duration > 0
            ? Math.min(dest, Math.max(0, video.duration - 2))
            : dest;
        video.currentTime = clamped;
        lastKnownPlayTimeRef.current = clamped;
        showHud('Resumed from ' + formatTime(clamped));
        targetSeekTimeRef.current = 0;
        video.play().catch(() => {});
      } catch {}
    }
  }, [resumeBannerRecord, isIframe, startIframeSeekRetry, showHud]);

  const restartPlaybackFromBeginning = useCallback(() => {
    setResumeBannerRecord(null);
    targetSeekTimeRef.current = 0;
    keepTimeRef.current = 0;
    pendingIframeSeekTimeRef.current = 0;
    if (iframeSeekRetryTimerRef.current) {
      clearInterval(iframeSeekRetryTimerRef.current);
      iframeSeekRetryTimerRef.current = null;
    }

    if (currentTarget) {
      const contentId = buildContentId(currentTarget);
      if (contentId.startsWith('series_')) {
        const existing = getContinueWatchingRecord(scopedKeyRef.current, contentId);
        if (existing) {
          saveContinueWatchingRecord(scopedKeyRef.current, {
            ...existing,
            currentTime: 0,
            progressPct: 0,
            isCompleted: false,
            updatedAt: Date.now(),
          });
        }
      } else {
        removeContinueWatchingRecord(scopedKeyRef.current, contentId);
      }
    }

    if (isIframe) {
      sendIframeSeek(0);
    } else if (videoRef.current) {
      try {
        videoRef.current.currentTime = 0;
        videoRef.current.play().catch(() => {});
      } catch {}
    }
    showHud('Playing from start');
  }, [currentTarget, isIframe, sendIframeSeek, showHud]);

  const dismissResumePrompt = useCallback(() => {
    setResumeBannerRecord(null);
  }, []);

  // Clear any pending watchdog
  const clearWatchdog = useCallback(() => {
    if (watchdogTimerRef.current) {
      clearTimeout(watchdogTimerRef.current);
      watchdogTimerRef.current = null;
    }
  }, []);

  // Automatic server fallback routine on reactive HLS fatal/404 errors (Vanilla L4980-4992, L5265-5302)
  const triggerAutoFallback = useCallback(
    (failedIdx: number, _errorReason?: string) => {
      clearWatchdog();
      const servers = streamInfoRef.current?.servers;
      if (!servers || servers.length <= 1) {
        if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
        setStatusNotice(null);
        setResolveError('Media unavailable across all servers for this title.');
        setShowRetryBtn(true);
        return;
      }

      failedServersRef.current.add(failedIdx);

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
        showHud(notice);
        setStatusNotice(notice);

        playbackStartedRef.current = false;
        setActiveServerIndex(nextIdx);
        setResolveError(null);
        setShowRetryBtn(false);

        if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
        noticeTimerRef.current = setTimeout(() => {
          setStatusNotice(null);
        }, 3500);

        startWatchdogRef.current(nextIdx);
      } else {
        if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
        setStatusNotice(null);
        setResolveError('Media unavailable across all servers for this title.');
        setShowRetryBtn(true);
      }
    },
    [clearWatchdog, showHud]
  );
  triggerAutoFallbackRef.current = triggerAutoFallback;

  // Watchdog (no speculative timer that kills cross-origin embeds)
  const startWatchdog = useCallback(
    (_serverIdx: number) => {
      clearWatchdog();
    },
    [clearWatchdog]
  );
  startWatchdogRef.current = startWatchdog;

  const handlePlaybackStarted = useCallback(() => {
    playbackStartedRef.current = true;
    clearWatchdog();
    if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
    setStatusNotice(null);
  }, [clearWatchdog]);

  // Continue Watching & Telemetry Hook
  const { currentTime, duration, hasVerifiedDuration, flushProgress } = usePlaybackProgress({
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

  // Check and trigger Next Episode popup when verified duration & remaining <= 180s (Vanilla L3674-3727)
  useEffect(() => {
    if (!isSeries || !currentTarget || !seriesData) {
      setNextEpPopup(null);
      return;
    }
    if (!hasVerifiedDuration || !duration || !Number.isFinite(duration) || duration <= 0) {
      return;
    }

    const REMAINING_THRESHOLD = 180;
    const remaining = duration - currentTime;
    let isEligible = false;
    if (duration > REMAINING_THRESHOLD) {
      isEligible = remaining > 0 && remaining <= REMAINING_THRESHOLD && currentTime >= 5;
    } else {
      isEligible = currentTime >= duration * 0.5 && remaining > 0 && currentTime >= 5;
    }
    if (!isEligible) return;

    const canonId = String(currentTarget.canonicalSeriesId || currentTarget.id);
    const epKey = `series_${canonId}_s${activeSeasonNum}_e${activeEpisodeNum}`;
    if (
      shownNextEpPopupKeyRef.current === epKey ||
      dismissedNextEpPopupKeyRef.current === epKey
    ) {
      return;
    }

    const next = getNextEpisodeInfo(activeSeasonNum, activeEpisodeNum, seriesData);
    if (!next || !next.hasNext) return;

    shownNextEpPopupKeyRef.current = epKey;
    setNextEpPopup(next);
  }, [
    isSeries,
    currentTarget,
    seriesData,
    hasVerifiedDuration,
    duration,
    currentTime,
    activeSeasonNum,
    activeEpisodeNum,
  ]);

  // Promote Next Episode dialog to Top Layer when in fullscreen (Vanilla L4648-4653, L5525-5535)
  useEffect(() => {
    const popup = nextEpDialogRef.current;
    if (!popup) return;
    if (nextEpPopup && isFullscreen && typeof popup.showModal === 'function') {
      try {
        if (!popup.open) popup.showModal();
      } catch {}
    } else if (!nextEpPopup && typeof popup.close === 'function' && popup.open) {
      try {
        popup.close();
      } catch {}
    }
  }, [nextEpPopup, isFullscreen]);

  const dismissNextEpisodePopup = useCallback((e?: React.MouseEvent) => {
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }
    const popup = nextEpDialogRef.current;
    if (popup && typeof popup.close === 'function' && popup.open) {
      try {
        popup.close();
      } catch {}
    }
    if (shownNextEpPopupKeyRef.current) {
      dismissedNextEpPopupKeyRef.current = shownNextEpPopupKeyRef.current;
    }
    setNextEpPopup(null);
  }, []);

  // Fetch Series Seasons Tree (Vanilla L4762-4799)
  const fetchSeasonsHierarchy = useCallback(async (movieId: number | string) => {
    if (seasonsAbortRef.current) {
      seasonsAbortRef.current.abort();
    }
    seasonsAbortRef.current = new AbortController();

    try {
      const data = await getSeriesSeasons(movieId, seasonsAbortRef.current.signal);
      if (data.is_series && data.seasons && data.seasons.length > 0) {
        setSeriesData(data);
        setSelectedSeasonTab((prev) => prev || data.current_season || 1);
      }
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      console.warn('Series seasons load failed:', err);
    }
  }, []);

  // Fullscreen state check helper (Vanilla L5449-5459)
  const checkIsPlayerInFullscreen = useCallback((): boolean => {
    const d = document as any;
    const v = videoRef.current as any;
    const container = playerContainerRef.current;
    return Boolean(
      d.fullscreenElement ||
        d.webkitFullscreenElement ||
        d.mozFullScreenElement ||
        d.msFullscreenElement ||
        (v && v.webkitDisplayingFullscreen) ||
        isPreservingEpisodeFsRef.current ||
        (container &&
          (container.classList.contains('is-fullscreen') ||
            container.classList.contains('fullscreen')))
    );
  }, []);

  // Episode transition handler (Vanilla L4880-4947)
  const handleSelectEpisode = useCallback(
    (seasonNum: number, episodeNum: number, epMovieId?: number | string | null) => {
      if (!currentTarget) return;
      if (isTransitioningRef.current) return;
      isTransitioningRef.current = true;
      window.setTimeout(() => {
        isTransitioningRef.current = false;
      }, 500);

      // Preserve fullscreen across episode transition (Vanilla L4881-4895)
      const wasInFs = checkIsPlayerInFullscreen();
      if (wasInFs) {
        isPreservingEpisodeFsRef.current = true;
        if (episodeFsPreserveTimerRef.current) clearTimeout(episodeFsPreserveTimerRef.current);
        playerContainerRef.current?.classList.add('is-fullscreen');
        document.body.classList.add('player-is-fullscreen');
        if (!document.fullscreenElement && playerContainerRef.current) {
          const c = playerContainerRef.current as any;
          const req =
            c.requestFullscreen ||
            c.webkitRequestFullscreen ||
            c.mozRequestFullScreen ||
            c.msRequestFullscreen;
          if (req) {
            try {
              Promise.resolve(req.call(c)).catch(() => {});
            } catch {}
          }
        }
        episodeFsPreserveTimerRef.current = setTimeout(() => {
          isPreservingEpisodeFsRef.current = false;
        }, 5000);
      }

      // Save outgoing episode progress
      flushProgressRef.current();

      // Reset popup & server tracking for new episode
      dismissNextEpisodePopup();
      shownNextEpPopupKeyRef.current = '';
      dismissedNextEpPopupKeyRef.current = '';
      isNextEpTransitioningRef.current = false;
      setIsNextEpLoading(false);

      clearWatchdog();
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
      setStatusNotice(`Playing Season ${seasonNum} Episode ${episodeNum}…`);
      attemptSeqRef.current += 1;
      failedServersRef.current.clear();
      playbackStartedRef.current = false;

      const targetMovieId = epMovieId ? Number(epMovieId) : currentTarget.id;
      const contentId = buildContentId({
        ...currentTarget,
        id: targetMovieId,
        isSeries: true,
        canonicalSeriesId: currentTarget.canonicalSeriesId || String(currentTarget.id),
        season: seasonNum,
        episode: episodeNum,
      });
      const savedRecord = getContinueWatchingRecord(scopedKeyRef.current, contentId);
      const resumeTime =
        savedRecord && !savedRecord.isCompleted && savedRecord.currentTime >= 5
          ? savedRecord.currentTime
          : 0;

      lastSyncedTargetKeyRef.current = `${targetMovieId}:${seasonNum}:${episodeNum}`;
      setCurrentTarget((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          id: targetMovieId,
          isSeries: true,
          season: seasonNum,
          episode: episodeNum,
          resumeTime,
        };
      });
      setSelectedSeasonTab(seasonNum);
    },
    [currentTarget, checkIsPlayerInFullscreen, dismissNextEpisodePopup, clearWatchdog]
  );

  // Trigger Play Next Episode button / shortcut (Vanilla L4681-4760)
  const triggerPlayNextEpisode = useCallback(
    (e?: React.MouseEvent) => {
      if (e) {
        e.stopPropagation();
        e.preventDefault();
      }
      if (isNextEpTransitioningRef.current) return;
      const next =
        nextEpPopup || getNextEpisodeInfo(activeSeasonNum, activeEpisodeNum, seriesDataRef.current);
      if (!next || !next.hasNext) {
        showHud('End of Series');
        dismissNextEpisodePopup();
        return;
      }
      isNextEpTransitioningRef.current = true;
      setIsNextEpLoading(true);
      showHud(`Playing ${next.label}`);
      handleSelectEpisode(next.season, next.episode, next.movieId);
    },
    [nextEpPopup, activeSeasonNum, activeEpisodeNum, showHud, dismissNextEpisodePopup, handleSelectEpisode]
  );

  // Fetch stream data from backend with sequence protection & progressive notices (Vanilla L5087-5170)
  const fetchStreamData = useCallback(
    async (
      targetId: number | string,
      season?: number | null,
      episode?: number | null,
      fresh: boolean = false
    ) => {
      const mySeq = ++resolveSeqRef.current;

      if (activeStreamAbortRef.current) {
        activeStreamAbortRef.current.abort();
      }
      const controller = new AbortController();
      activeStreamAbortRef.current = controller;

      if (slowNoticeTimerRef.current) clearTimeout(slowNoticeTimerRef.current);
      if (timeoutNoticeTimerRef.current) clearTimeout(timeoutNoticeTimerRef.current);
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);

      setIsResolving(true);
      setResolveError(null);
      setShowRetryBtn(false);
      const epLabel = season != null && episode != null ? ` S${season} E${episode}` : '';
      setStatusNotice(`Resolving stream${epLabel} from high-speed servers…`);

      // Vanilla L5097-5108: Progressive timeout notices at 12s and 45s without aborting network request
      slowNoticeTimerRef.current = setTimeout(() => {
        if (mySeq === resolveSeqRef.current) {
          setStatusNotice(`Contacting stream servers${epLabel} (first-time initialization)…`);
        }
      }, 12000);

      timeoutNoticeTimerRef.current = setTimeout(() => {
        if (mySeq === resolveSeqRef.current) {
          setResolveError('Stream resolution is taking longer than usual.');
          setShowRetryBtn(true);
        }
      }, 45000);

      try {
        const info = await resolveStream(targetId, {
          fresh,
          season,
          episode,
          signal: controller.signal,
        });

        if (slowNoticeTimerRef.current) clearTimeout(slowNoticeTimerRef.current);
        if (timeoutNoticeTimerRef.current) clearTimeout(timeoutNoticeTimerRef.current);

        if (mySeq !== resolveSeqRef.current || controller.signal.aborted) {
          return;
        }

        attemptSeqRef.current += 1;
        failedServersRef.current.clear();
        playbackStartedRef.current = false;
        setStatusNotice(null);
        setResolveError(null);
        setShowRetryBtn(false);
        streamInfoRef.current = info;
        setStreamInfo(info);
        setActiveServerIndex(0);
        setIsResolving(false);

        if (info.servers && info.servers.length > 0) {
          startWatchdogRef.current(0);
        } else {
          setResolveError('No playable stream available for this title across verified sources.');
          setShowRetryBtn(true);
        }
      } catch (err: any) {
        if (slowNoticeTimerRef.current) clearTimeout(slowNoticeTimerRef.current);
        if (timeoutNoticeTimerRef.current) clearTimeout(timeoutNoticeTimerRef.current);

        if (err.name === 'AbortError' || mySeq !== resolveSeqRef.current) {
          return;
        }
        setStatusNotice(null);
        setResolveError(err.message || 'No playable stream for this title.');
        setShowRetryBtn(true);
        setIsResolving(false);
      }
    },
    []
  );

  const targetId = currentTarget?.id;
  const targetSeason = currentTarget?.season;
  const targetEpisode = currentTarget?.episode;
  const targetIsSeries = Boolean(currentTarget?.isSeries);

  // Resolve stream & metadata when opened or target identity changes (Vanilla L4573-4600)
  useEffect(() => {
    if (!isOpen || targetId == null) {
      setStreamInfo(null);
      setIsResolving(false);
      setResolveError(null);
      setShowRetryBtn(false);
      return;
    }

    fetchStreamData(targetId, targetSeason, targetEpisode, false);

    let metaCancelled = false;
    fetch(`/api/movie/${targetId}`, { credentials: 'include' })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!metaCancelled && data) {
          setMovieMeta(data);
        }
      })
      .catch(() => {});

    if (targetIsSeries || targetSeason != null || targetEpisode != null) {
      fetchSeasonsHierarchy(targetId);
    }

    return () => {
      metaCancelled = true;
      clearWatchdog();
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
      if (slowNoticeTimerRef.current) clearTimeout(slowNoticeTimerRef.current);
      if (timeoutNoticeTimerRef.current) clearTimeout(timeoutNoticeTimerRef.current);
      if (activeStreamAbortRef.current) {
        activeStreamAbortRef.current.abort();
      }
      if (seasonsAbortRef.current) {
        seasonsAbortRef.current.abort();
      }
    };
  }, [
    isOpen,
    targetId,
    targetSeason,
    targetEpisode,
    targetIsSeries,
    fetchStreamData,
    fetchSeasonsHierarchy,
    clearWatchdog,
  ]);

  // Self-heal callback on expired stream token (Vanilla L5177-5195)
  const handleSelfHeal = useCallback(() => {
    if (targetId == null) return;
    const video = videoRef.current;
    const resumeAt = Math.max(
      video && !isNaN(video.currentTime) && video.currentTime > 5 ? video.currentTime : 0,
      lastKnownPlayTimeRef.current || 0
    );
    if (resumeAt > 3) {
      targetSeekTimeRef.current = resumeAt;
      keepTimeRef.current = resumeAt;
      lastKnownPlayTimeRef.current = resumeAt;
    }
    setStatusNotice(
      `Token refreshed — resuming playback${resumeAt > 0 ? ' at ' + formatTime(resumeAt) : ''}…`
    );
    fetchStreamData(targetId, targetSeason, targetEpisode, true);
  }, [targetId, targetSeason, targetEpisode, fetchStreamData]);

  // Hls.js hook for native HLS streams
  useHlsPlayer({
    videoRef,
    src: hlsSource,
    autoPlay: true,
    initialSeekTime: currentTarget?.resumeTime || keepTimeRef.current || 0,
    onSelfHeal: handleSelfHeal,
    onFatalError: (msg) => {
      triggerAutoFallbackRef.current(activeServerIndex, msg);
    },
  });

  // Toggle English Subtitles (Vanilla L4313-4324)
  const toggleCC = useCallback(() => {
    const video = videoRef.current;
    if (!video || !video.textTracks || video.textTracks.length === 0) {
      showHud('No Subtitles');
      return;
    }
    const track = video.textTracks[0];
    const isShowing = track.mode === 'showing';
    track.mode = isShowing ? 'hidden' : 'showing';
    setCcEnabled(!isShowing);
    showHud(`Subtitles: ${isShowing ? 'OFF' : 'English'}`);
  }, [showHud]);

  // 10s Skip Handler with Instant Recovery (Vanilla L4161-4223)
  const handleSkip = useCallback(
    (direction: number) => {
      if (isIframe) {
        showHud('Seeking handled via player controls in embed');
        return;
      }
      const video = videoRef.current;
      if (!video) return;

      const wasPlaying =
        isActivelyPlayingRef.current ||
        !video.paused ||
        video.seeking ||
        isSeekingActiveRef.current;
      if (wasPlaying) isActivelyPlayingRef.current = true;

      if (direction > 0) {
        if (skipAccumulatorRef.current < 0) skipAccumulatorRef.current = 0;
        skipAccumulatorRef.current += 10;
      } else {
        if (skipAccumulatorRef.current > 0) skipAccumulatorRef.current = 0;
        skipAccumulatorRef.current -= 10;
      }

      const vidDur =
        video.duration && !isNaN(video.duration) && isFinite(video.duration)
          ? video.duration
          : 999999;
      const baseTime =
        seekTargetTimeRef.current !== null && isSeekingActiveRef.current
          ? seekTargetTimeRef.current
          : video.currentTime;
      const nextSeek = Math.max(0, Math.min(vidDur - 1, baseTime + direction * 10));
      seekTargetTimeRef.current = nextSeek;
      isSeekingActiveRef.current = true;

      if (typeof (video as any).fastSeek === 'function') {
        try {
          (video as any).fastSeek(nextSeek);
        } catch {
          video.currentTime = nextSeek;
        }
      } else {
        video.currentTime = nextSeek;
      }

      const text =
        skipAccumulatorRef.current > 0
          ? `⏩ +${skipAccumulatorRef.current}s`
          : `⏪ ${skipAccumulatorRef.current}s`;
      showHud(text);

      if (skipResetTimerRef.current) clearTimeout(skipResetTimerRef.current);
      skipResetTimerRef.current = setTimeout(() => {
        skipAccumulatorRef.current = 0;
        seekTargetTimeRef.current = null;
        isSeekingActiveRef.current = false;
      }, 750);

      if (wasPlaying && video.paused) {
        const p = video.play();
        if (p && typeof p.catch === 'function') {
          p.catch(() => {
            const onReady = () => {
              video.removeEventListener('canplay', onReady);
              video.removeEventListener('seeked', onReady);
              if (isActivelyPlayingRef.current && video.paused) {
                video.play().catch(() => {});
              }
            };
            video.addEventListener('canplay', onReady, { once: true });
            video.addEventListener('seeked', onReady, { once: true });
          });
        }
      }
    },
    [isIframe, showHud]
  );

  // W3C MediaSession API for Smart TV Remotes (Vanilla L4269-4310)
  useEffect(() => {
    if (!isOpen || !currentTarget || !('mediaSession' in navigator)) return;
    try {
      const mediaTitle =
        cleanTitle(seriesData?.title || movieMeta?.title || currentTarget.title) || 'CineMyMovies';
      const mediaPoster = movieMeta?.poster || currentTarget.poster || '';

      navigator.mediaSession.metadata = new MediaMetadata({
        title: mediaTitle,
        artist: 'CineMyMovies',
        album: 'Movies & TV',
        artwork: mediaPoster ? [{ src: mediaPoster, sizes: '512x512', type: 'image/jpeg' }] : [],
      });

      navigator.mediaSession.setActionHandler('seekforward', (details) => {
        const sec = (details && details.seekOffset) || 10;
        handleSkip(Math.round(sec / 10) || 1);
      });
      navigator.mediaSession.setActionHandler('seekbackward', (details) => {
        const sec = (details && details.seekOffset) || 10;
        handleSkip(-(Math.round(sec / 10) || 1));
      });
      navigator.mediaSession.setActionHandler('nexttrack', () => {
        handleSkip(1);
      });
      navigator.mediaSession.setActionHandler('previoustrack', () => {
        handleSkip(-1);
      });
      navigator.mediaSession.setActionHandler('play', () => {
        const video = videoRef.current;
        if (video && video.paused) {
          video.play().catch(() => {});
          isActivelyPlayingRef.current = true;
          showHud('▶ Play');
        }
      });
      navigator.mediaSession.setActionHandler('pause', () => {
        const video = videoRef.current;
        if (video && !video.paused) {
          video.pause();
          isActivelyPlayingRef.current = false;
          showHud('⏸ Pause');
        }
      });
      try {
        navigator.mediaSession.setActionHandler('seekto', (details) => {
          const video = videoRef.current;
          if (video && details.seekTime !== undefined && !isNaN(details.seekTime)) {
            video.currentTime = details.seekTime;
            if (isActivelyPlayingRef.current) video.play().catch(() => {});
          }
        });
      } catch {}
    } catch {}
  }, [isOpen, currentTarget, seriesData?.title, movieMeta, handleSkip, showHud]);

  // Native video playback state listeners (Vanilla L4240-4266)
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !isOpen) return;

    const onPlay = () => {
      isActivelyPlayingRef.current = true;
      setIsVideoPlaying(true);
    };
    const onPlaying = () => {
      isActivelyPlayingRef.current = true;
      setIsVideoPlaying(true);
      setStatusNotice(null);
      if (video.currentTime > 3) {
        lastKnownPlayTimeRef.current = video.currentTime;
      }
    };
    const onPause = () => {
      if (!video.seeking && !isSeekingActiveRef.current) {
        isActivelyPlayingRef.current = false;
        setIsVideoPlaying(false);
      }
    };
    const onWaiting = () => {
      if (!isIframe) {
        setStatusNotice('Buffering…');
      }
    };
    const onSeeked = () => {
      if (video.currentTime > 3) {
        lastKnownPlayTimeRef.current = video.currentTime;
      }
      if (isActivelyPlayingRef.current && video.paused) {
        video.play().catch(() => {});
      }
    };
    const onCanPlay = () => {
      if (isActivelyPlayingRef.current && video.paused) {
        video.play().catch(() => {});
      }
    };

    setIsVideoPlaying(!video.paused && !video.ended);
    video.addEventListener('play', onPlay);
    video.addEventListener('playing', onPlaying);
    video.addEventListener('pause', onPause);
    video.addEventListener('waiting', onWaiting);
    video.addEventListener('seeked', onSeeked);
    video.addEventListener('canplay', onCanPlay);

    return () => {
      video.removeEventListener('play', onPlay);
      video.removeEventListener('playing', onPlaying);
      video.removeEventListener('pause', onPause);
      video.removeEventListener('waiting', onWaiting);
      video.removeEventListener('seeked', onSeeked);
      video.removeEventListener('canplay', onCanPlay);
    };
  }, [isOpen, Boolean(currentTarget), isIframe, isNativeVideo]);

  // Fullscreen Idle Activity & State Change (Vanilla L5434-5602)
  const triggerFsActivity = useCallback(() => {
    const d = document as any;
    const isFs = Boolean(
      d.fullscreenElement ||
        d.webkitFullscreenElement ||
        d.mozFullScreenElement ||
        d.msFullscreenElement
    );
    if (!isFs) return;
    playerContainerRef.current?.classList.remove('fs-idle');
    if (videoRef.current && videoRef.current.style.display !== 'none' && !videoRef.current.controls) {
      videoRef.current.controls = true;
    }
    if (fsActivityTimerRef.current) clearTimeout(fsActivityTimerRef.current);
    fsActivityTimerRef.current = setTimeout(() => {
      const stillFs = Boolean(
        d.fullscreenElement ||
          d.webkitFullscreenElement ||
          d.mozFullScreenElement ||
          d.msFullscreenElement
      );
      if (stillFs) {
        playerContainerRef.current?.classList.add('fs-idle');
      }
    }, 4000);
  }, []);

  const handleFsStateChange = useCallback(() => {
    const d = document as any;
    const fsElement =
      d.fullscreenElement ||
      d.webkitFullscreenElement ||
      d.mozFullScreenElement ||
      d.msFullscreenElement;
    const isFs = Boolean(fsElement);

    if (isFs) {
      document.body.classList.add('player-is-fullscreen');
      playerContainerRef.current?.classList.add('is-fullscreen');
      setIsFullscreen(true);
      triggerFsActivity();
    } else {
      if (isPreservingEpisodeFsRef.current || isNextEpTransitioningRef.current) {
        playerContainerRef.current?.classList.add('is-fullscreen');
        document.body.classList.add('player-is-fullscreen');
        setIsFullscreen(true);
        return;
      }
      document.body.classList.remove('player-is-fullscreen');
      playerContainerRef.current?.classList.remove('is-fullscreen');
      playerContainerRef.current?.classList.remove('fs-idle');
      setIsFullscreen(false);
      if (videoRef.current) videoRef.current.controls = true;
      if (fsActivityTimerRef.current) clearTimeout(fsActivityTimerRef.current);
    }
  }, [triggerFsActivity]);

  useEffect(() => {
    if (!isOpen) return;
    const events = [
      'fullscreenchange',
      'webkitfullscreenchange',
      'mozfullscreenchange',
      'MSFullscreenChange',
    ];
    events.forEach((evt) => document.addEventListener(evt, handleFsStateChange));
    window.addEventListener('mousemove', triggerFsActivity);
    window.addEventListener('touchstart', triggerFsActivity, { passive: true });
    return () => {
      events.forEach((evt) => document.removeEventListener(evt, handleFsStateChange));
      window.removeEventListener('mousemove', triggerFsActivity);
      window.removeEventListener('touchstart', triggerFsActivity);
    };
  }, [isOpen, handleFsStateChange, triggerFsActivity]);

  // Toggle Player Fullscreen (Vanilla L5461-5512)
  const togglePlayerFullscreen = useCallback(() => {
    isPreservingEpisodeFsRef.current = false;
    isNextEpTransitioningRef.current = false;
    if (episodeFsPreserveTimerRef.current) clearTimeout(episodeFsPreserveTimerRef.current);

    const isFs = checkIsPlayerInFullscreen();
    const d = document as any;
    const v = videoRef.current as any;
    const container = playerContainerRef.current as any;
    const pIframe = iframeRef.current as any;

    if (isFs) {
      if (v && v.webkitDisplayingFullscreen && typeof v.webkitExitFullscreen === 'function') {
        try {
          v.webkitExitFullscreen();
        } catch {}
      }
      const ex =
        d.exitFullscreen ||
        d.webkitExitFullscreen ||
        d.mozCancelFullScreen ||
        d.msExitFullscreen;
      if (
        ex &&
        (d.fullscreenElement ||
          d.webkitFullscreenElement ||
          d.mozFullScreenElement ||
          d.msFullscreenElement)
      ) {
        try {
          Promise.resolve(ex.call(document)).catch(() => {});
        } catch {}
      }
      if (container) {
        container.classList.remove('is-fullscreen');
        container.classList.remove('fullscreen');
        container.classList.remove('fs-idle');
      }
      document.body.classList.remove('player-is-fullscreen');
      setIsFullscreen(false);
      showHud('Exited Fullscreen');
    } else {
      if (container) {
        container.classList.add('is-fullscreen');
      }
      document.body.classList.add('player-is-fullscreen');
      setIsFullscreen(true);

      const activeEl =
        pIframe && pIframe.style.display !== 'none'
          ? pIframe
          : v && v.style.display !== 'none'
          ? v
          : container;
      const fsTarget = container || activeEl;
      const req =
        fsTarget &&
        (fsTarget.requestFullscreen ||
          fsTarget.webkitRequestFullscreen ||
          fsTarget.mozRequestFullScreen ||
          fsTarget.msRequestFullscreen);
      if (req) {
        Promise.resolve(req.call(fsTarget)).catch(() => {
          if (v && v.style.display !== 'none') {
            const vReq =
              v.requestFullscreen || v.webkitRequestFullscreen || v.webkitEnterFullscreen;
            if (vReq) {
              try {
                vReq.call(v);
              } catch {}
            }
          }
        });
      } else if (v && v.style.display !== 'none') {
        const vReq = v.requestFullscreen || v.webkitRequestFullscreen || v.webkitEnterFullscreen;
        if (vReq) {
          try {
            vReq.call(v);
          } catch {}
        }
      }
      showHud('Fullscreen');
    }
  }, [checkIsPlayerInFullscreen, showHud]);

  // Video surface click in container fullscreen (Vanilla L5572-5584)
  const handleVideoSurfaceClick = useCallback(
    (event: React.MouseEvent<HTMLVideoElement>) => {
      if ((event.nativeEvent as any)?.pointerType === 'touch') return;
      const d = document as any;
      const fsElement =
        d.fullscreenElement ||
        d.webkitFullscreenElement ||
        d.mozFullScreenElement ||
        d.msFullscreenElement;
      const video = videoRef.current;
      if (fsElement !== playerContainerRef.current || !video || video.style.display === 'none') {
        return;
      }
      const rect = video.getBoundingClientRect();
      if (event.clientY >= rect.bottom - 72) return;
      event.preventDefault();
      event.stopPropagation();
      if (video.paused || video.ended) video.play().catch(() => {});
      else video.pause();
      triggerFsActivity();
    },
    [triggerFsActivity]
  );

  // Double click left or right half of playerContainer to skip 10s (Vanilla L4226-4237)
  const handleContainerDoubleClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (isIframe) {
        showHud('Seeking handled via player controls in embed');
        return;
      }
      const tgt = e.target as HTMLElement;
      if (tgt && tgt.tagName === 'BUTTON') return;
      const container = playerContainerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      if (e.clientY >= rect.bottom - 72) return;
      const x = e.clientX - rect.left;
      if (x < rect.width * 0.45) {
        handleSkip(-1);
      } else if (x > rect.width * 0.55) {
        handleSkip(1);
      }
    },
    [handleSkip, isIframe, showHud]
  );

  // Close player handler (Vanilla L5308-5396)
  const handleClose = useCallback(() => {
    clearWatchdog();
    if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
    if (slowNoticeTimerRef.current) clearTimeout(slowNoticeTimerRef.current);
    if (timeoutNoticeTimerRef.current) clearTimeout(timeoutNoticeTimerRef.current);
    if (episodeFsPreserveTimerRef.current) clearTimeout(episodeFsPreserveTimerRef.current);
    if (fsActivityTimerRef.current) clearTimeout(fsActivityTimerRef.current);
    if (iframeSeekRetryTimerRef.current) clearInterval(iframeSeekRetryTimerRef.current);

    isPreservingEpisodeFsRef.current = false;
    isNextEpTransitioningRef.current = false;
    setStatusNotice(null);
    setShowRetryBtn(false);
    setNextEpPopup(null);
    setResumeBannerRecord(null);
    flushProgress();

    // Exit fullscreen if active
    const d = document as any;
    if (d.fullscreenElement || d.webkitFullscreenElement || d.mozFullScreenElement) {
      const ex = d.exitFullscreen || d.webkitExitFullscreen || d.mozCancelFullScreen;
      if (ex) {
        try {
          Promise.resolve(ex.call(document)).catch(() => {});
        } catch {}
      }
    }
    if (playerContainerRef.current) {
      playerContainerRef.current.classList.remove('is-fullscreen');
      playerContainerRef.current.classList.remove('fullscreen');
      playerContainerRef.current.classList.remove('fs-idle');
    }
    document.body.classList.remove('player-is-fullscreen');

    // Reset media elements
    if (iframeRef.current) {
      iframeRef.current.style.display = 'none';
      setIframeSrc('about:blank');
    }
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.removeAttribute('src');
      videoRef.current.load();
    }

    onClose();
  }, [clearWatchdog, flushProgress, setIframeSrc, onClose]);

  // Activate Stream Server (Vanilla L4997-5085)
  const handleSelectServer = useCallback(
    (index: number) => {
      if (!streamInfo || !streamInfo.servers || index >= streamInfo.servers.length) return;
      flushProgress();
      clearWatchdog();
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
      setStatusNotice(null);
      setResolveError(null);
      setShowRetryBtn(false);
      failedServersRef.current.delete(index);
      playbackStartedRef.current = false;

      const curWatchTime = Math.max(
        videoRef.current && !isNaN(videoRef.current.currentTime) && videoRef.current.currentTime > 3
          ? videoRef.current.currentTime
          : 0,
        currentTime > 3 ? currentTime : 0,
        targetSeekTimeRef.current || 0,
        keepTimeRef.current || 0,
        lastKnownPlayTimeRef.current || 0
      );

      const nextSrv = streamInfo.servers[index];
      setActiveServerIndex(index);

      if (curWatchTime > 3) {
        if (nextSrv.kind === 'iframe') {
          setTimeout(() => startIframeSeekRetry(curWatchTime), 150);
          showHud('Resumed from ' + formatTime(curWatchTime));
        } else {
          targetSeekTimeRef.current = curWatchTime;
          keepTimeRef.current = curWatchTime;
          showHud('Resumed from ' + formatTime(curWatchTime));
        }
      }

      startWatchdogRef.current(index);
    },
    [streamInfo, flushProgress, clearWatchdog, currentTime, startIframeSeekRetry, showHud]
  );

  // Scroll Modal to Episodes (Vanilla L4840-4849)
  const scrollModalToEpisodes = useCallback(() => {
    const seasonsWrap = seasonsSectionRef.current;
    if (seasonsWrap && seasonsWrap.style.display !== 'none') {
      seasonsWrap.scrollIntoView({ block: 'start', behavior: 'smooth' });
      const tab =
        seasonsWrap.querySelector<HTMLElement>('.season-tab-btn.active') ||
        seasonsWrap.querySelector<HTMLElement>('.season-tab-btn') ||
        seasonsWrap.querySelector<HTMLElement>('.ep-chip.active');
      if (tab) {
        setTimeout(() => tab.focus(), 250);
      }
    } else {
      window.scrollBy({ top: 320, behavior: 'smooth' });
    }
  }, []);

  // Update #btn-scroll-episodes on window scroll (Vanilla L4851-4873)
  useEffect(() => {
    if (!isOpen) return;
    const onScroll = () => {
      const seasonsWrap = seasonsSectionRef.current;
      if (!seasonsWrap) {
        setIsScrolledPastEpisodes(false);
        return;
      }
      setIsScrolledPastEpisodes(window.scrollY > seasonsWrap.offsetTop - 140);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, [isOpen, seriesData]);

  // Complete Vanilla TV Remote & Keyboard Capture Listener (Vanilla L5606-6062)
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      // 1. Check Back / Exit key first across all TV remotes (Android, Samsung Tizen, LG webOS, Fire TV)
      if (isBackOrExitKey(e)) {
        if (checkIsPlayerInFullscreen()) {
          e.preventDefault();
          e.stopPropagation();
          togglePlayerFullscreen();
          return;
        }
        e.preventDefault();
        e.stopPropagation();
        handleClose();
        return;
      }

      const active = document.activeElement as HTMLElement | null;
      if (active && (active.tagName === 'INPUT' || active.tagName === 'SELECT')) {
        if (e.key === 'Escape') active.blur();
        return;
      }

      const isFs = checkIsPlayerInFullscreen();
      const key = e.key || '';
      const code = e.code || '';
      const keyCode = (e as any).keyCode || (e as any).which || 0;
      const video = videoRef.current;

      // 2. TV Remote Media Keys (Vanilla L5641-5706)
      const isSkipForwardKey =
        key === 'MediaFastForward' ||
        key === 'FastFwd' ||
        key === 'MediaTrackNext' ||
        key === 'TrackNext' ||
        key === 'MediaSkipForward' ||
        key === 'MediaStepForward' ||
        code === 'MediaFastForward' ||
        code === 'MediaTrackNext' ||
        keyCode === 228 ||
        keyCode === 417 ||
        keyCode === 90 ||
        keyCode === 272 ||
        keyCode === 274 ||
        keyCode === 176 ||
        keyCode === 10233 ||
        keyCode === 425;

      const isSkipBackwardKey =
        key === 'MediaRewind' ||
        key === 'Rewind' ||
        key === 'MediaTrackPrevious' ||
        key === 'TrackPrevious' ||
        key === 'MediaSkipBackward' ||
        key === 'MediaStepBackward' ||
        code === 'MediaRewind' ||
        code === 'MediaTrackPrevious' ||
        keyCode === 227 ||
        keyCode === 412 ||
        keyCode === 89 ||
        keyCode === 273 ||
        keyCode === 275 ||
        keyCode === 177 ||
        keyCode === 10232 ||
        keyCode === 424;

      const isPlayPauseKey =
        key === 'MediaPlayPause' ||
        key === 'MediaPlay' ||
        key === 'MediaPause' ||
        code === 'MediaPlayPause' ||
        keyCode === 179 ||
        keyCode === 10252 ||
        keyCode === 415 ||
        keyCode === 19 ||
        keyCode === 85 ||
        keyCode === 126 ||
        keyCode === 127;

      if (isSkipForwardKey) {
        e.preventDefault();
        e.stopPropagation();
        handleSkip(1);
        return;
      }
      if (isSkipBackwardKey) {
        e.preventDefault();
        e.stopPropagation();
        handleSkip(-1);
        return;
      }
      if (isPlayPauseKey && video) {
        e.preventDefault();
        e.stopPropagation();
        if (key === 'MediaPause' || keyCode === 19 || keyCode === 127) {
          video.pause();
          isActivelyPlayingRef.current = false;
          showHud('⏸ Pause');
        } else if (key === 'MediaPlay' || keyCode === 415 || keyCode === 126) {
          video.play().catch(() => {});
          isActivelyPlayingRef.current = true;
          showHud('▶ Play');
        } else {
          if (video.paused) {
            video.play().catch(() => {});
            isActivelyPlayingRef.current = true;
            showHud('▶ Play');
          } else {
            video.pause();
            isActivelyPlayingRef.current = false;
            showHud('⏸ Pause');
          }
        }
        return;
      }

      // 3. Keyboard Shortcuts ('f', 'm', 'c', 'n') (Vanilla L5708-5734)
      if (key === 'f' || key === 'F') {
        e.preventDefault();
        togglePlayerFullscreen();
        return;
      }
      if ((key === 'm' || key === 'M') && video) {
        e.preventDefault();
        video.muted = !video.muted;
        showHud(video.muted ? '🔇 Muted' : '🔊 Unmuted');
        return;
      }
      if (key === 'c' || key === 'C') {
        e.preventDefault();
        toggleCC();
        return;
      }
      if (key === 'n' || key === 'N') {
        const next = getNextEpisodeInfo(activeSeasonNum, activeEpisodeNum, seriesDataRef.current);
        if (next && next.hasNext) {
          e.preventDefault();
          triggerPlayNextEpisode();
        }
        return;
      }

      const isLeftArrow = key === 'ArrowLeft' || code === 'ArrowLeft' || keyCode === 37;
      const isRightArrow = key === 'ArrowRight' || code === 'ArrowRight' || keyCode === 39;
      const isUpArrow = key === 'ArrowUp' || code === 'ArrowUp' || keyCode === 38;
      const isDownArrow = key === 'ArrowDown' || code === 'ArrowDown' || keyCode === 40;

      // 4. FULLSCREEN MODE: Arrow keys skip 10s and adjust volume (Vanilla L5741-5784)
      if (isFs) {
        if (isRightArrow) {
          e.preventDefault();
          e.stopPropagation();
          handleSkip(1);
          return;
        }
        if (isLeftArrow) {
          e.preventDefault();
          e.stopPropagation();
          handleSkip(-1);
          return;
        }
        if (isUpArrow && video) {
          e.preventDefault();
          e.stopPropagation();
          video.volume = Math.min(1, Math.round((video.volume + 0.1) * 10) / 10);
          showHud(`🔊 Volume ${Math.round(video.volume * 100)}%`);
          return;
        }
        if (isDownArrow && video) {
          e.preventDefault();
          e.stopPropagation();
          video.volume = Math.max(0, Math.round((video.volume - 0.1) * 10) / 10);
          showHud(`🔉 Volume ${Math.round(video.volume * 100)}%`);
          return;
        }
        if (
          (key === ' ' || code === 'Space' || key === 'k' || key === 'K' || keyCode === 32) &&
          video
        ) {
          e.preventDefault();
          e.stopPropagation();
          if (video.paused) {
            video.play().catch(() => {});
            isActivelyPlayingRef.current = true;
            showHud('▶ Play');
          } else {
            video.pause();
            isActivelyPlayingRef.current = false;
            showHud('⏸ Pause');
          }
          return;
        }
        return;
      }

      // 5. WINDOWED MODAL MODE: Full TV Remote D-Pad Navigation & Smooth Scrolling (Vanilla L5786-6061)
      const isDown = key === 'ArrowDown' || key === 'Down' || keyCode === 40;
      const isUp = key === 'ArrowUp' || key === 'Up' || keyCode === 38;
      const isLeft = key === 'ArrowLeft' || key === 'Left' || keyCode === 37;
      const isRight = key === 'ArrowRight' || key === 'Right' || keyCode === 39;

      if (key === 'PageDown' || key === 'ChannelDown' || keyCode === 34 || keyCode === 428) {
        e.preventDefault();
        window.scrollBy({ top: 320, behavior: 'smooth' });
        return;
      }
      if (key === 'PageUp' || key === 'ChannelUp' || keyCode === 33 || keyCode === 427) {
        e.preventDefault();
        window.scrollBy({ top: -320, behavior: 'smooth' });
        return;
      }

      const isTopBtn = Boolean(
        active &&
          (active.closest('.btn-group') ||
            active.classList.contains('btn-close') ||
            active.closest('.watch-nav'))
      );
      const isSeasonBtn = Boolean(active && active.classList.contains('season-tab-btn'));
      const isEpChip = Boolean(active && active.classList.contains('ep-chip'));
      const isSrvBtn = Boolean(active && active.closest('#server-switcher'));
      const isAltBtn = Boolean(active && active.closest('#alt-source-wrap'));
      const isResumeBtn = Boolean(active && active.closest('#resume-banner'));
      const isNextEpBtn = Boolean(active && active.closest('#next-ep-popup'));
      const seasonsWrap = document.getElementById('series-seasons-wrap');
      const hasSeasonsDom = Boolean(seasonsWrap && seasonsWrap.style.display !== 'none');

      if (isDown) {
        e.preventDefault();
        if (isTopBtn) {
          const srvSwitcher = document.getElementById('server-switcher');
          const srvBtn =
            srvSwitcher?.querySelector<HTMLElement>('button.active') ||
            srvSwitcher?.querySelector<HTMLElement>('button');
          if (srvSwitcher && srvSwitcher.style.display !== 'none' && srvBtn) {
            srvBtn.focus();
            srvBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
          } else {
            const scrollBtn = document.getElementById('btn-scroll-episodes');
            if (scrollBtn && scrollBtn.style.display !== 'none') {
              scrollBtn.focus();
              scrollBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
            } else if (hasSeasonsDom) {
              scrollModalToEpisodes();
            } else {
              window.scrollBy({ top: 220, behavior: 'smooth' });
            }
          }
        } else if (isSrvBtn || isAltBtn || isResumeBtn || isNextEpBtn) {
          const scrollBtn = document.getElementById('btn-scroll-episodes');
          if (scrollBtn && scrollBtn.style.display !== 'none') {
            scrollBtn.focus();
            scrollBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
          } else if (hasSeasonsDom) {
            scrollModalToEpisodes();
          } else {
            window.scrollBy({ top: 220, behavior: 'smooth' });
          }
        } else if (active && active.id === 'btn-scroll-episodes') {
          scrollModalToEpisodes();
        } else if (isSeasonBtn && seasonsWrap) {
          const epChips = Array.from(
            seasonsWrap.querySelectorAll<HTMLElement>('.episodes-grid .ep-chip')
          );
          if (epChips.length > 0) {
            const activeChip =
              seasonsWrap.querySelector<HTMLElement>('.episodes-grid .ep-chip.active') ||
              epChips[0];
            activeChip.focus();
            activeChip.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
          } else {
            window.scrollBy({ top: 200, behavior: 'smooth' });
          }
        } else if (isEpChip && seasonsWrap && active) {
          const epChips = Array.from(
            seasonsWrap.querySelectorAll<HTMLElement>('.episodes-grid .ep-chip')
          );
          const idx = epChips.indexOf(active);
          if (idx !== -1) {
            let cols = 1;
            const curTop = active.offsetTop;
            for (let i = idx + 1; i < epChips.length; i++) {
              if (epChips[i].offsetTop > curTop) {
                cols = i - idx;
                break;
              }
            }
            if (cols === 1 && idx > 0) {
              const r0 = epChips[0].offsetTop;
              for (let i = 1; i < epChips.length; i++) {
                if (epChips[i].offsetTop > r0) {
                  cols = i;
                  break;
                }
              }
            }
            if (cols < 1) cols = 6;
            const nextIdx = idx + cols;
            if (nextIdx < epChips.length) {
              epChips[nextIdx].focus();
              epChips[nextIdx].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            } else {
              window.scrollBy({ top: 180, behavior: 'smooth' });
            }
          }
        } else {
          if (hasSeasonsDom && seasonsWrap) {
            const tab =
              seasonsWrap.querySelector<HTMLElement>('.season-tab-btn.active') ||
              seasonsWrap.querySelector<HTMLElement>('.season-tab-btn');
            if (tab) {
              tab.focus();
              tab.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            } else {
              window.scrollBy({ top: 200, behavior: 'smooth' });
            }
          } else {
            window.scrollBy({ top: 200, behavior: 'smooth' });
          }
        }
        return;
      }

      if (isUp) {
        e.preventDefault();
        if (active && active.id === 'btn-scroll-episodes') {
          const srvSwitcher = document.getElementById('server-switcher');
          const srvBtn =
            srvSwitcher?.querySelector<HTMLElement>('button.active') ||
            srvSwitcher?.querySelector<HTMLElement>('button');
          if (srvSwitcher && srvSwitcher.style.display !== 'none' && srvBtn) {
            srvBtn.focus();
            srvBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
          } else {
            const topBtn =
              document.querySelector<HTMLElement>('#overlay .btn-close') ||
              document.querySelector<HTMLElement>('#overlay .btn-group button');
            if (topBtn) topBtn.focus();
            window.scrollTo({ top: 0, behavior: 'smooth' });
          }
        } else if (isEpChip && seasonsWrap && active) {
          const epChips = Array.from(
            seasonsWrap.querySelectorAll<HTMLElement>('.episodes-grid .ep-chip')
          );
          const idx = epChips.indexOf(active);
          if (idx !== -1) {
            let cols = 1;
            const curTop = active.offsetTop;
            for (let i = idx + 1; i < epChips.length; i++) {
              if (epChips[i].offsetTop > curTop) {
                cols = i - idx;
                break;
              }
            }
            if (cols === 1 && idx > 0) {
              const r0 = epChips[0].offsetTop;
              for (let i = 1; i < epChips.length; i++) {
                if (epChips[i].offsetTop > r0) {
                  cols = i;
                  break;
                }
              }
            }
            if (cols < 1) cols = 6;
            const prevIdx = idx - cols;
            if (prevIdx >= 0) {
              epChips[prevIdx].focus();
              epChips[prevIdx].scrollIntoView({ block: 'center', behavior: 'smooth' });
            } else {
              const tab =
                seasonsWrap.querySelector<HTMLElement>('.season-tab-btn.active') ||
                seasonsWrap.querySelector<HTMLElement>('.season-tab-btn') ||
                document.getElementById('btn-scroll-episodes');
              if (tab) {
                tab.focus();
                tab.scrollIntoView({ block: 'center', behavior: 'smooth' });
              }
            }
          }
        } else if (isSeasonBtn) {
          const scrollBtn = document.getElementById('btn-scroll-episodes');
          if (scrollBtn && scrollBtn.style.display !== 'none') {
            scrollBtn.focus();
            scrollBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
          } else {
            const topBtn =
              document.querySelector<HTMLElement>('#overlay .btn-close') ||
              document.querySelector<HTMLElement>('#overlay .btn-group button');
            if (topBtn) topBtn.focus();
            window.scrollTo({ top: 0, behavior: 'smooth' });
          }
        } else if (isSrvBtn || isAltBtn) {
          const topBtn =
            document.querySelector<HTMLElement>('#overlay .btn-close') ||
            document.querySelector<HTMLElement>('#overlay .btn-group button') ||
            document.querySelector<HTMLElement>('#btn-watch-back');
          if (topBtn) topBtn.focus();
          window.scrollTo({ top: 0, behavior: 'smooth' });
        } else {
          window.scrollBy({ top: -220, behavior: 'smooth' });
        }
        return;
      }

      if (isRight) {
        if (isSeasonBtn && seasonsWrap && active) {
          e.preventDefault();
          const tabs = Array.from(seasonsWrap.querySelectorAll<HTMLElement>('.season-tab-btn'));
          const idx = tabs.indexOf(active);
          if (idx !== -1 && idx + 1 < tabs.length) {
            tabs[idx + 1].focus();
            tabs[idx + 1].scrollIntoView({ inline: 'nearest', behavior: 'smooth' });
          }
          return;
        }
        if (isEpChip && seasonsWrap && active) {
          e.preventDefault();
          const chips = Array.from(
            seasonsWrap.querySelectorAll<HTMLElement>('.episodes-grid .ep-chip')
          );
          const idx = chips.indexOf(active);
          if (idx !== -1 && idx + 1 < chips.length) {
            chips[idx + 1].focus();
            chips[idx + 1].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
          }
          return;
        }
        if (isTopBtn && active) {
          e.preventDefault();
          const btns = Array.from(
            document.querySelectorAll<HTMLElement>(
              '#overlay .watch-nav button, #overlay .row .btn-close, #overlay .btn-group button'
            )
          ).filter((b) => b.style.display !== 'none' && (b.offsetWidth > 0 || b.offsetHeight > 0));
          const idx = btns.indexOf(active);
          if (idx !== -1 && idx + 1 < btns.length) {
            btns[idx + 1].focus();
          }
          return;
        }
        if ((isSrvBtn || isAltBtn || isResumeBtn || isNextEpBtn) && active) {
          e.preventDefault();
          const container = active.closest(
            '#server-switcher, #alt-source-wrap, #resume-banner, #next-ep-popup'
          );
          if (container) {
            const btns = Array.from(container.querySelectorAll<HTMLElement>('button'));
            const idx = btns.indexOf(active);
            if (idx !== -1 && idx + 1 < btns.length) {
              btns[idx + 1].focus();
            }
          }
          return;
        }
        e.preventDefault();
        handleSkip(1);
        return;
      }

      if (isLeft) {
        if (isSeasonBtn && seasonsWrap && active) {
          e.preventDefault();
          const tabs = Array.from(seasonsWrap.querySelectorAll<HTMLElement>('.season-tab-btn'));
          const idx = tabs.indexOf(active);
          if (idx > 0) {
            tabs[idx - 1].focus();
            tabs[idx - 1].scrollIntoView({ inline: 'nearest', behavior: 'smooth' });
          }
          return;
        }
        if (isEpChip && seasonsWrap && active) {
          e.preventDefault();
          const chips = Array.from(
            seasonsWrap.querySelectorAll<HTMLElement>('.episodes-grid .ep-chip')
          );
          const idx = chips.indexOf(active);
          if (idx > 0) {
            chips[idx - 1].focus();
            chips[idx - 1].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
          }
          return;
        }
        if (isTopBtn && active) {
          e.preventDefault();
          const btns = Array.from(
            document.querySelectorAll<HTMLElement>(
              '#overlay .watch-nav button, #overlay .row .btn-close, #overlay .btn-group button'
            )
          ).filter((b) => b.style.display !== 'none' && (b.offsetWidth > 0 || b.offsetHeight > 0));
          const idx = btns.indexOf(active);
          if (idx > 0) {
            btns[idx - 1].focus();
          }
          return;
        }
        if ((isSrvBtn || isAltBtn || isResumeBtn || isNextEpBtn) && active) {
          e.preventDefault();
          const container = active.closest(
            '#server-switcher, #alt-source-wrap, #resume-banner, #next-ep-popup'
          );
          if (container) {
            const btns = Array.from(container.querySelectorAll<HTMLElement>('button'));
            const idx = btns.indexOf(active);
            if (idx > 0) {
              btns[idx - 1].focus();
            }
          }
          return;
        }
        e.preventDefault();
        handleSkip(-1);
        return;
      }

      if (key === ' ' || code === 'Space' || key === 'k' || key === 'K' || keyCode === 32) {
        if (active && active.tagName === 'BUTTON') return;
        if (video && !isIframe) {
          e.preventDefault();
          if (video.paused) {
            video.play().catch(() => {});
            showHud('▶ Play');
          } else {
            video.pause();
            showHud('⏸ Pause');
          }
        }
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown, true);
    return () => window.removeEventListener('keydown', handleKeyDown, true);
  }, [
    isOpen,
    isIframe,
    activeSeasonNum,
    activeEpisodeNum,
    checkIsPlayerInFullscreen,
    togglePlayerFullscreen,
    handleClose,
    handleSkip,
    toggleCC,
    triggerPlayNextEpisode,
    scrollModalToEpisodes,
    showHud,
  ]);

  // Document watch-page lifecycle, initial focus & scroll restoration (Vanilla L4364-4477, L5351-5396)
  useEffect(() => {
    if (isOpen) {
      homeScrollYRef.current = window.scrollY || 0;
      document.body.classList.remove('modal-open');
      document.body.classList.add('watch-page');
      window.scrollTo({ top: 0, behavior: 'auto' });

      const focusTimer = setTimeout(() => {
        const firstBtn =
          document.querySelector<HTMLElement>('#overlay .btn-close') ||
          document.querySelector<HTMLElement>('#overlay .btn-group button');
        if (firstBtn && typeof firstBtn.focus === 'function') {
          firstBtn.focus();
        }
      }, 120);

      return () => {
        clearTimeout(focusTimer);
        document.body.classList.remove('watch-page');
        const savedScroll = homeScrollYRef.current;
        if (savedScroll > 0) {
          setTimeout(() => window.scrollTo({ top: savedScroll, behavior: 'auto' }), 0);
        }
      };
    } else {
      document.body.classList.remove('watch-page');
    }
  }, [isOpen]);

  if (!isOpen || !currentTarget) return null;

  const effectiveSource = movieMeta?.source || currentTarget.source;
  const effectiveHindiDubbed = Boolean(movieMeta?.is_hindi_dubbed ?? currentTarget.isHindiDubbed);
  const rawTitle = seriesData?.title || movieMeta?.title || currentTarget.title || `Movie #${currentTarget.id}`;
  const baseTitle = cleanTitle(rawTitle);
  const epSuffix = isSeries
    ? ` · S${String(activeSeasonNum).padStart(2, '0')} E${String(activeEpisodeNum).padStart(2, '0')}`
    : '';
  const hasYearInTitle = /\(\s*\d{4}\s*\)/.test(rawTitle);
  const effectiveYear = movieMeta?.year || currentTarget.year;
  const yr = effectiveYear && !hasYearInTitle ? ` (${effectiveYear})` : '';

  const activeSeasonData =
    seriesData?.seasons?.find((s) => Number(s.season_number) === Number(selectedSeasonTab)) ||
    seriesData?.seasons?.[0];

  const hasSeasons = Boolean(seriesData?.seasons && seriesData.seasons.length > 0);
  const synopsisText = (
    movieMeta?.synopsis ||
    movieMeta?.description ||
    (streamInfo as any)?.description ||
    currentTarget.synopsis ||
    ''
  ).trim();
  const effectiveGenres =
    movieMeta?.genres || movieMeta?.genre || currentTarget.genres || (streamInfo as any)?.genres;
  const hasMetaOrSyn = Boolean(
    synopsisText ||
      movieMeta?.rating ||
      currentTarget.rating ||
      movieMeta?.duration_s ||
      currentTarget.duration_s ||
      movieMeta?.quality ||
      currentTarget.quality ||
      (Array.isArray(effectiveGenres) ? effectiveGenres.length > 0 : effectiveGenres) ||
      (Array.isArray(movieMeta?.country) ? movieMeta.country.length > 0 : movieMeta?.country)
  );

  const sameSources: any[] =
    movieMeta?.available_sources || movieMeta?.also_available_on || [];
  const otherEditions: any[] = movieMeta?.other_editions || [];
  const hasAltSources = sameSources.length > 0 || otherEditions.length > 0;

  const getSourceBadge = (source?: string) => {
    const s = (source || 'yomovies').toLowerCase();
    if (s.includes('ask')) return <span className="src-badge ask">🍿 ask</span>;
    if (s.includes('doo')) return <span className="src-badge doo">▶️ doo</span>;
    if (s.includes('movie7') || s.includes('m7')) return <span className="src-badge m7">⚡ 7</span>;
    return <span className="src-badge ym">🎬 ym</span>;
  };

  const getSourceLabel = (source?: string) => {
    if (source === 'ask4movie') return '🍿 Ask4Movies';
    if (source === 'dooflix') return '▶️ DooFlix';
    if (source === 'movies7') return '⚡ 7';
    return '🎬 YoMovies';
  };

  const getEditionLabel = (ed?: string) => {
    const map: Record<string, string> = {
      hindi_dubbed: 'Hindi Dubbed',
      dual_audio: 'Dual Audio',
      hindi: 'Hindi',
      english: 'English',
      unknown: 'Other',
    };
    return (ed && map[ed]) || 'Other';
  };

  const handleSwitchAltEdition = (altId: number) => {
    if (!altId) return;
    flushProgress();
    lastSyncedTargetKeyRef.current = `${altId}:${currentTarget.season ?? ''}:${currentTarget.episode ?? ''}`;
    setCurrentTarget((prev) => (prev ? { ...prev, id: Number(altId) } : null));
  };

  return (
    <div
      id="overlay"
      className="prod-player-overlay on"
      ref={overlayRef}
    >
      <div className="box prod-player-box">
        {/* 1. Watch Navigation Bar (Vanilla L2482-2485) */}
        <div className="watch-nav">
          <button
            id="btn-watch-back"
            type="button"
            className="btn-watch-back"
            onClick={handleClose}
            title="Back to Home"
          >
            &larr; Back to Home
          </button>
          <span className="watch-kicker">Now Watching</span>
        </div>

        {/* 2. Title & Action Buttons Row (Vanilla L2486-2494) */}
        <div className="row prod-player-title-row">
          <h2 id="p-title" className="prod-player-title" title={`${baseTitle}${epSuffix}${yr}`}>
            {getSourceBadge(effectiveSource)}{' '}
            {effectiveHindiDubbed && <span className="dub-badge">🎙️ Hindi Dubbed</span>}{' '}
            <span className="title-text">
              {baseTitle}
              {epSuffix}
              {yr}
            </span>
          </h2>
          <button
            type="button"
            className="btn-close"
            onClick={handleClose}
            title="Close Player (Escape)"
          >
            ✕ Close
          </button>
          <div className="btn-group">
            <button
              id="btn-rewind"
              type="button"
              className="btn-action"
              style={{ display: isIframe ? 'none' : 'inline-flex' }}
              onClick={() => handleSkip(-1)}
              title="Rewind 10s (Left Arrow / Click)"
            >
              ⏪ -10s
            </button>
            <button
              id="btn-forward"
              type="button"
              className="btn-action"
              style={{ display: isIframe ? 'none' : 'inline-flex' }}
              onClick={() => handleSkip(1)}
              title="Skip Forward 10s (Right Arrow / Click)"
            >
              ⏩ +10s
            </button>
            <button
              id="btn-cc"
              type="button"
              className="btn-action"
              style={{ display: isIframe ? 'none' : 'inline-flex' }}
              onClick={toggleCC}
              title="Toggle English Subtitles (Press C)"
            >
              CC: English ({ccEnabled ? 'ON' : 'OFF'})
            </button>
          </div>
        </div>

        {/* 3. Server Switcher (Vanilla L2495, L5145-5158) */}
        <div
          id="server-switcher"
          className="prod-server-switcher"
          style={{
            display:
              streamInfo && streamInfo.servers && streamInfo.servers.length > 1 && !isResolving ? 'flex' : 'none',
            gap: '8px',
            padding: '8px 0 12px',
            flexWrap: 'wrap',
            alignItems: 'center',
          }}
        >
          {streamInfo?.servers?.map((srv, idx) => {
            const isSelected = idx === activeServerIndex;
            return (
              <button
                key={`srv-pill-${idx}`}
                type="button"
                className={`pill${isSelected ? ' active' : ''}`}
                style={{ padding: '4px 12px', fontSize: '12px', cursor: 'pointer' }}
                onClick={() => handleSelectServer(idx)}
              >
                {srv.label || `Server ${idx + 1}`}
              </button>
            );
          })}
        </div>

        {/* 4. Player Container (Vanilla L2496-2530) — Zero covering loading/error overlays */}
        <div
          className="player-container"
          id="player-container"
          ref={playerContainerRef}
          onDoubleClick={handleContainerDoubleClick}
        >
          <video
            ref={videoRef}
            id="v"
            controls
            playsInline
            controlsList="noremoteplayback"
            onClick={handleVideoSurfaceClick}
            style={{
              display: isNativeVideo ? 'block' : 'none',
              width: '100%',
              height: '100%',
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
                onLoad={() => {
                  const v = videoRef.current;
                  if (v && v.textTracks && v.textTracks[0]) {
                    v.textTracks[0].mode = 'showing';
                  }
                }}
              />
            )}
          </video>

          {/* Persistent Embed Iframe (Vanilla L2499, L4326-4361) */}
          <iframe
            ref={iframeRef}
            id="p-iframe"
            src={isIframe && activeServer?.url ? activeServer.url : undefined}
            style={{
              display: isIframe ? 'block' : 'none',
              width: '100%',
              height: '100%',
              border: 0,
              position: 'absolute',
              inset: 0,
              zIndex: 1,
            }}
            allow="accelerometer *; autoplay *; clipboard-write *; encrypted-media *; gyroscope *; picture-in-picture *; web-share *; fullscreen *"
            allowFullScreen={true}
            // @ts-ignore
            webkitallowfullscreen="true"
            // @ts-ignore
            mozallowfullscreen="true"
            referrerPolicy="no-referrer"
            title="Video Player Stream"
          />

          {/* Floating HUD Badge (Vanilla L2500) */}
          <div id="player-hud" className={hudVisible ? 'show' : ''}>
            {hudText}
          </div>

          {/* Resume Playback Banner (Vanilla L2501-2511) */}
          <div
            id="resume-banner"
            className="resume-banner"
            style={{ display: resumeBannerRecord ? 'flex' : 'none' }}
          >
            <div className="resume-info">
              <span>⏱️</span>
              <span id="resume-text">
                {resumeBannerRecord
                  ? `Resume from ${formatTime(resumeBannerRecord.currentTime)}?`
                  : 'Resume playback?'}
              </span>
            </div>
            <div className="resume-buttons">
              <button
                id="btn-resume-now"
                type="button"
                className="btn-resume-action"
                onClick={confirmResumePlayback}
                tabIndex={0}
              >
                {resumeBannerRecord
                  ? `▶️ Resume from ${formatTime(resumeBannerRecord.currentTime)}`
                  : '▶️ Resume'}
              </button>
              <button
                id="btn-restart-now"
                type="button"
                className="btn-resume-action btn-resume-secondary"
                onClick={restartPlaybackFromBeginning}
                tabIndex={0}
              >
                🔄 Start Over
              </button>
              <button
                type="button"
                className="btn-resume-close"
                onClick={dismissResumePrompt}
                title="Dismiss"
                tabIndex={0}
              >
                &times;
              </button>
            </div>
          </div>

          {/* Next Episode Overlay Popup (Vanilla L2513-2529) */}
          {nextEpPopup && (
            <dialog
              id="next-ep-popup"
              ref={nextEpDialogRef}
              className="next-ep-popup"
              style={{ display: 'flex' }}
              role="dialog"
              aria-label="Next Episode"
              onClick={(e) => e.stopPropagation()}
              onPointerDown={(e) => e.stopPropagation()}
              onMouseDown={(e) => e.stopPropagation()}
            >
              <div className="next-ep-details">
                <div className="next-ep-badge">NEXT EPISODE</div>
                <div className="next-ep-title" id="next-ep-title">
                  {nextEpPopup.fullTitle || nextEpPopup.label || ''}
                </div>
                <div className="next-ep-meta" id="next-ep-meta">
                  {`Up next in ${nextEpPopup.label}`}
                </div>
              </div>
              <div className="next-ep-actions">
                <button
                  id="btn-next-ep-play"
                  type="button"
                  className="btn-next-ep-play"
                  disabled={isNextEpLoading}
                  onClick={triggerPlayNextEpisode}
                  tabIndex={0}
                  title="Play Next Episode"
                >
                  <svg className="icon-play" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                    <path d="M8 5v14l11-7z" fill="currentColor" />
                  </svg>
                  <span id="btn-next-ep-text">
                    {isNextEpLoading ? 'Loading…' : 'Play Next'}
                  </span>
                </button>
                <button
                  type="button"
                  className="btn-next-ep-dismiss"
                  onClick={dismissNextEpisodePopup}
                  tabIndex={0}
                  title="Dismiss (✕)"
                >
                  &times;
                </button>
              </div>
            </dialog>
          )}
        </div>

        {/* 5. Alternate Sources / Editions (Vanilla L2531, L4555-4567) */}
        <div
          id="alt-source-wrap"
          style={{
            display: hasAltSources ? 'block' : 'none',
            marginTop: '8px',
            fontSize: '12.5px',
            color: 'var(--dim)',
          }}
        >
          {sameSources.length > 0 && (
            <div>
              <span>Same-edition sources:</span>{' '}
              {sameSources.map((alt) => (
                <button
                  key={`alt-same-${alt.id}`}
                  type="button"
                  className="pill"
                  style={{
                    display: 'inline-block',
                    margin: '3px 0 3px 6px',
                    padding: '3px 10px',
                    fontSize: '11.5px',
                    background: 'var(--card)',
                    border: '1px solid var(--border)',
                    color: 'var(--txt)',
                    borderRadius: '12px',
                    cursor: 'pointer',
                  }}
                  onClick={() => handleSwitchAltEdition(alt.id)}
                >
                  Switch to {getSourceLabel(alt.source)}
                </button>
              ))}
            </div>
          )}
          {otherEditions.length > 0 && (
            <div style={{ marginTop: '5px' }}>
              <span>Other editions:</span>{' '}
              {otherEditions.map((alt) => (
                <button
                  key={`alt-ed-${alt.id}`}
                  type="button"
                  className="pill"
                  style={{
                    display: 'inline-block',
                    margin: '3px 0 3px 6px',
                    padding: '3px 10px',
                    fontSize: '11.5px',
                    background: 'var(--card)',
                    border: '1px solid var(--border)',
                    color: 'var(--txt)',
                    borderRadius: '12px',
                    cursor: 'pointer',
                  }}
                  onClick={() => handleSwitchAltEdition(alt.id)}
                >
                  {getEditionLabel(alt.audio_edition)} · {getSourceLabel(alt.source)}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 6. Status & Retry Wrap (Vanilla L2532-2537) */}
        <div className="status-wrap">
          <div className="status prod-player-status" id="p-status">
            {resolveError ? (
              <span style={{ color: '#ff8888' }}>⚠️ {resolveError}</span>
            ) : statusNotice || isResolving ? (
              <>
                <span className="spinner" />
                <span>
                  {statusNotice ||
                    `Resolving stream${
                      isSeries ? ` S${activeSeasonNum} E${activeEpisodeNum}` : ''
                    } from high-speed servers…`}
                </span>
              </>
            ) : (
              <span>
                {activeServer?.label || `Server ${activeServerIndex + 1}`}
                {isSeries ? ` · S${activeSeasonNum} E${activeEpisodeNum}` : ''} · Active stream
                player
              </span>
            )}
          </div>
          <div
            id="retry-wrap"
            style={{ display: showRetryBtn || Boolean(resolveError) ? 'block' : 'none' }}
          >
            <button
              type="button"
              className="btn-retry"
              onClick={() => {
                failedServersRef.current.clear();
                lastIframeSrcRef.current = 'about:blank';
                setActiveServerIndex(0);
                if (targetId != null) {
                  fetchStreamData(targetId, targetSeason, targetEpisode, true);
                }
              }}
            >
              🔄 Retry Stream
            </button>
          </div>
        </div>

        {/* 7. Scroll Episodes Button (Vanilla L2538-2541, L4851-4873) */}
        <button
          id="btn-scroll-episodes"
          type="button"
          className="btn-scroll-episodes"
          style={{ display: isSeries && hasSeasons ? 'inline-flex' : 'none' }}
          onClick={() => {
            if (isScrolledPastEpisodes) {
              window.scrollTo({ top: 0, behavior: 'smooth' });
            } else {
              scrollModalToEpisodes();
            }
          }}
          title="Jump down to Episodes & Seasons"
          tabIndex={0}
        >
          <span id="scroll-episodes-icon">{isScrolledPastEpisodes ? '⌃' : '⌄'}</span>
          <span id="scroll-episodes-text">
            {isScrolledPastEpisodes ? 'Back to Player' : 'Episodes & Seasons'}
          </span>
        </button>

        {/* 8. Series Seasons & Episodes Grid (Vanilla L2542, L4801-4838) */}
        <div
          id="series-seasons-wrap"
          className="series-seasons-wrap"
          ref={seasonsSectionRef}
          style={{ display: isSeries && hasSeasons ? 'block' : 'none' }}
        >
          {isSeries && hasSeasons && (
            <>
              <div className="seasons-top-bar">
                <div className="seasons-title">
                  <span>📺</span>
                  <span>{seriesData?.title || 'Episodes'}</span>
                  <span className="seasons-count-badge">
                    {activeSeasonData?.episode_count || activeSeasonData?.episodes?.length || 0}{' '}
                    Episodes
                  </span>
                </div>
              </div>

              <div className="seasons-nav" role="tablist" aria-label="Series Seasons">
                {seriesData?.seasons?.map((s) => {
                  const sNum = Number(s.season_number);
                  const isTabActive = sNum === Number(selectedSeasonTab);
                  return (
                    <button
                      key={`season-tab-${sNum}`}
                      type="button"
                      className={`season-tab-btn${isTabActive ? ' active' : ''}`}
                      onClick={() => setSelectedSeasonTab(sNum)}
                      role="tab"
                      aria-selected={isTabActive}
                    >
                      {s.name || `Season ${sNum}`} ({s.episode_count || s.episodes?.length || 0})
                    </button>
                  );
                })}
              </div>

              <div className="episodes-grid" role="list" aria-label="Season Episodes">
                {activeSeasonData?.episodes?.map((ep) => {
                  const epNum = ep.episode_number ?? ep.e;
                  const isEpActive = ep.s === activeSeasonNum && epNum === activeEpisodeNum;
                  const label = `Ep ${epNum}`;
                  const fullTitle = `${ep.name || label}${
                    ep.movie_id && ep.movie_id !== currentTarget.id ? ' (Native)' : ''
                  }`;

                  return (
                    <button
                      key={`ep-chip-${ep.s}-${epNum}`}
                      type="button"
                      className={`ep-chip${isEpActive ? ' active' : ''}`}
                      title={fullTitle}
                      onClick={() => handleSelectEpisode(ep.s, epNum, ep.movie_id)}
                      role="listitem"
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {/* 9. Watch Details & Synopsis (Vanilla L2543-2547, L4542-4553) */}
        <div
          id="p-details"
          className="watch-details"
          ref={detailsRef}
          style={{ display: hasMetaOrSyn ? 'block' : 'none' }}
        >
          <div id="p-meta" className="watch-meta">
            {(movieMeta?.rating || currentTarget.rating) && (
              <span>Rating {movieMeta?.rating || currentTarget.rating}</span>
            )}
            {(movieMeta?.duration_s || currentTarget.duration_s) && (
              <span>
                {Math.max(
                  1,
                  Math.round(Number(movieMeta?.duration_s || currentTarget.duration_s) / 60)
                )}{' '}
                min
              </span>
            )}
            {(movieMeta?.quality || currentTarget.quality) && (
              <span>{movieMeta?.quality || currentTarget.quality}</span>
            )}
            {effectiveGenres && (
              <span>
                {Array.isArray(effectiveGenres)
                  ? effectiveGenres.join(', ')
                  : effectiveGenres}
              </span>
            )}
            {movieMeta?.country && (
              <span>
                {Array.isArray(movieMeta.country)
                  ? movieMeta.country.join(', ')
                  : movieMeta.country}
              </span>
            )}
          </div>
          {synopsisText && <h3 className="watch-syn-title">Synopsis</h3>}
          <p className="syn watch-syn-text" id="p-syn">
            {synopsisText}
          </p>
        </div>
      </div>
    </div>
  );
};
