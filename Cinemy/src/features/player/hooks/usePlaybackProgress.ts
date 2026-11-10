import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../../../context/AuthContext';
import {
  resolveContinueWatchingKey,
  getContinueWatchingRecord,
  saveContinueWatchingRecord,
  removeContinueWatchingRecord,
} from '../../continue-watching/storage';
import { PlaybackTarget } from '../types';
import { buildContentId, isPermittedIframeOrigin } from '../services/playerService';

interface UsePlaybackProgressOptions {
  target: PlaybackTarget | null;
  videoRef: React.RefObject<HTMLVideoElement>;
  iframeRef: React.RefObject<HTMLIFrameElement>;
  isIframe: boolean;
  activeIframeOrigin: string | null;
  streamSrc?: string | null;
  isResolving?: boolean;
  onEnded?: () => void;
  onPlaybackStarted?: () => void;
}

export function usePlaybackProgress({
  target,
  videoRef,
  iframeRef,
  isIframe,
  activeIframeOrigin,
  streamSrc,
  isResolving,
  onEnded,
  onPlaybackStarted,
}: UsePlaybackProgressOptions) {
  const { username, role, authenticated } = useAuth();
  const scopedKey = resolveContinueWatchingKey(username, role, authenticated);

  const onPlaybackStartedRef = useRef(onPlaybackStarted);
  onPlaybackStartedRef.current = onPlaybackStarted;

  const [currentTime, setCurrentTime] = useState<number>(target?.resumeTime || 0);
  const [duration, setDuration] = useState<number | null>(null);
  const [hasVerifiedDuration, setHasVerifiedDuration] = useState<boolean>(false);
  const [isEnded, setIsEnded] = useState<boolean>(false);

  const lastSaveTimeRef = useRef<number>(0);
  const prevTargetRef = useRef<PlaybackTarget | null>(null);
  const iframeBaseOffsetRef = useRef<number>(target?.resumeTime || 0);
  const iframeWatchStartRef = useRef<number>(Date.now());
  const hasConfirmedPlaybackRef = useRef<boolean>(false);

  const progressRef = useRef({
    currentTime: target?.resumeTime || 0,
    duration: null as number | null,
    hasVerifiedDuration: false,
    isEnded: false,
  });

  progressRef.current = {
    currentTime,
    duration,
    hasVerifiedDuration,
    isEnded,
  };

  // Target transition: flush previous content progress and initialize new target
  useEffect(() => {
    const prev = prevTargetRef.current;
    if (
      prev &&
      target &&
      (prev.id !== target.id || prev.season !== target.season || prev.episode !== target.episode)
    ) {
      const { currentTime: cur, duration: dur, hasVerifiedDuration: verified, isEnded: ended } =
        progressRef.current;

      if (cur >= 5 && hasConfirmedPlaybackRef.current) {
        const prevContentId = buildContentId(prev);
        const isSeries = Boolean(prev.isSeries);
        const validDuration =
          Number.isFinite(dur) && (dur ?? 0) > 0 ? Math.floor(dur!) : (prev.duration_s || null);

        if (!isSeries && verified && validDuration && validDuration >= 300 && cur / validDuration >= 0.95) {
          removeContinueWatchingRecord(scopedKey, prevContentId);
        } else {
          saveContinueWatchingRecord(scopedKey, {
            contentId: prevContentId,
            id: prev.id,
            series_id: isSeries ? (prev.canonicalSeriesId || prev.id) : null,
            title: prev.title,
            poster: prev.poster || null,
            year: prev.year || null,
            is_series: isSeries,
            season: isSeries ? (prev.season ?? 1) : null,
            episode: isSeries ? (prev.episode ?? 1) : null,
            source: prev.source || 'yomovies',
            is_hindi_dubbed: Boolean(prev.isHindiDubbed),
            currentTime: Math.floor(cur),
            duration: validDuration,
            hasVerifiedDuration: Boolean(verified && validDuration),
            progressPct:
              validDuration && validDuration > 0
                ? Math.min(100, Math.round((cur / validDuration) * 100))
                : 0,
            isCompleted: isSeries ? Boolean(ended) : false,
            updatedAt: Date.now(),
          });
        }
      }

      // Read existing saved progress for new target
      const contentId = buildContentId(target);
      const existingSaved = getContinueWatchingRecord(scopedKey, contentId);
      const legitimateSavedTime =
        existingSaved && Number.isFinite(existingSaved.currentTime) && existingSaved.currentTime >= 5
          ? existingSaved.currentTime
          : 0;

      const initResume = target.resumeTime || legitimateSavedTime || 0;
      setCurrentTime(initResume);
      setDuration(null);
      setHasVerifiedDuration(false);
      setIsEnded(false);
      lastSaveTimeRef.current = 0;
      iframeBaseOffsetRef.current = initResume;
      iframeWatchStartRef.current = Date.now();
      hasConfirmedPlaybackRef.current = false;
      progressRef.current = {
        currentTime: initResume,
        duration: null,
        hasVerifiedDuration: false,
        isEnded: false,
      };
    } else if (!prev && target) {
      const contentId = buildContentId(target);
      const existingSaved = getContinueWatchingRecord(scopedKey, contentId);
      const legitimateSavedTime =
        existingSaved && Number.isFinite(existingSaved.currentTime) && existingSaved.currentTime >= 5
          ? existingSaved.currentTime
          : 0;

      const initResume = target.resumeTime || legitimateSavedTime || 0;
      if (initResume > 0) {
        setCurrentTime(initResume);
        progressRef.current.currentTime = initResume;
      }
      iframeBaseOffsetRef.current = initResume;
      iframeWatchStartRef.current = Date.now();
      hasConfirmedPlaybackRef.current = false;
    }
    prevTargetRef.current = target;
  }, [target, scopedKey]);

  // Unified save progress callback matching Vanilla savePlaybackProgress (L3564-3666)
  const saveProgress = useCallback(
    (force: boolean = false, overrideCur?: number, overrideDur?: number | null) => {
      if (!target) return;

      const cur = overrideCur !== undefined ? overrideCur : progressRef.current.currentTime;
      const dur =
        overrideDur !== undefined
          ? overrideDur
          : progressRef.current.duration ?? (target.duration_s || null);
      const verified = progressRef.current.hasVerifiedDuration;
      const ended = progressRef.current.isEnded;

      if (cur < 5 && !ended) return;

      // Requirement 1 & 2 & 3: Protect existing legitimate resume position
      const contentId = buildContentId(target);
      const existingRecord = getContinueWatchingRecord(scopedKey, contentId);
      const existingSavedTime =
        existingRecord && Number.isFinite(existingRecord.currentTime) ? existingRecord.currentTime : 0;

      // If an existing legitimate position exists (>= 5s), an unconfirmed or speculative lower timestamp must NEVER overwrite it!
      if (!force && existingSavedTime >= 5 && cur < existingSavedTime - 2) {
        return;
      }

      // If playback has never been confirmed on an iframe, do not write speculative wall-clock time
      if (isIframe && !hasConfirmedPlaybackRef.current && !ended && !verified) {
        return;
      }

      const isSeries = Boolean(target.isSeries);
      const validDuration =
        Number.isFinite(dur) && (dur ?? 0) > 0 ? Math.floor(dur!) : null;

      // 1. Movies: 95% completion threshold removes item from Continue Watching (Vanilla L3616-3628)
      if (!isSeries) {
        const isCompletedMovie =
          ended ||
          Boolean(
            verified &&
              validDuration &&
              validDuration >= 300 &&
              cur / validDuration >= 0.95
          );
        if (isCompletedMovie) {
          removeContinueWatchingRecord(scopedKey, contentId);
          return;
        }
      }

      // Throttle non-forced saves to roughly every 10 seconds (Vanilla L3636-3640)
      if (
        !force &&
        !ended &&
        lastSaveTimeRef.current > 0 &&
        Math.abs(cur - lastSaveTimeRef.current) < 9.5
      ) {
        return;
      }
      lastSaveTimeRef.current = cur;

      const progressPct =
        validDuration && validDuration > 0
          ? Math.min(100, Math.round((cur / validDuration) * 100))
          : 0;

      // 2. Web Series Episodes: ONLY genuine ended events mark completion (Vanilla L3630-3634)
      const isCompleted = isSeries ? Boolean(ended) : false;

      saveContinueWatchingRecord(scopedKey, {
        contentId,
        id: target.id,
        series_id: isSeries ? (target.canonicalSeriesId || target.id) : null,
        title: target.title,
        poster: target.poster || null,
        year: target.year || null,
        is_series: isSeries,
        season: isSeries ? (target.season ?? 1) : null,
        episode: isSeries ? (target.episode ?? 1) : null,
        source: target.source || 'yomovies',
        is_hindi_dubbed: Boolean(target.isHindiDubbed),
        currentTime: Math.floor(cur),
        duration: validDuration,
        hasVerifiedDuration: Boolean(verified && validDuration),
        progressPct: isCompleted ? 100 : progressPct,
        isCompleted,
        updatedAt: Date.now(),
      });
    },
    [target, scopedKey, isIframe]
  );

  const flushProgress = useCallback(() => {
    saveProgress(true);
  }, [saveProgress]);

  // Native HTML5 Video telemetry listeners (Vanilla L3730-3772)
  useEffect(() => {
    if (isIframe) return;
    const video = videoRef.current;
    if (!video) return;

    const handleTimeUpdate = () => {
      if (isNaN(video.currentTime)) return;
      const cur = video.currentTime;
      const dur = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : null;

      if (cur > 0 && !video.paused) {
        hasConfirmedPlaybackRef.current = true;
        onPlaybackStartedRef.current?.();
      }

      progressRef.current.currentTime = cur;
      if (dur) {
        progressRef.current.duration = dur;
        progressRef.current.hasVerifiedDuration = true;
      }

      setCurrentTime(cur);
      saveProgress(false, cur, dur);
    };

    const handlePlay = () => {
      hasConfirmedPlaybackRef.current = true;
      onPlaybackStartedRef.current?.();
    };

    const handleDurationChange = () => {
      if (Number.isFinite(video.duration) && video.duration > 0) {
        setDuration(video.duration);
        setHasVerifiedDuration(true);
        progressRef.current.duration = video.duration;
        progressRef.current.hasVerifiedDuration = true;
      }
    };

    const handlePause = () => {
      const cur = video.currentTime;
      const dur = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : null;
      progressRef.current.currentTime = cur;
      saveProgress(true, cur, dur);
    };

    const handleEnded = () => {
      setIsEnded(true);
      progressRef.current.isEnded = true;
      saveProgress(true, video.currentTime, video.duration);
      onEnded?.();
    };

    video.addEventListener('timeupdate', handleTimeUpdate);
    video.addEventListener('play', handlePlay);
    video.addEventListener('playing', handlePlay);
    video.addEventListener('durationchange', handleDurationChange);
    video.addEventListener('loadedmetadata', handleDurationChange);
    video.addEventListener('pause', handlePause);
    video.addEventListener('ended', handleEnded);

    return () => {
      video.removeEventListener('timeupdate', handleTimeUpdate);
      video.removeEventListener('play', handlePlay);
      video.removeEventListener('playing', handlePlay);
      video.removeEventListener('durationchange', handleDurationChange);
      video.removeEventListener('loadedmetadata', handleDurationChange);
      video.removeEventListener('pause', handlePause);
      video.removeEventListener('ended', handleEnded);
    };
  }, [isIframe, videoRef, streamSrc, isResolving, saveProgress, onEnded]);

  // Vanilla startIframeWatchTracker (L2844-2880): 1s wall-clock tracker for embeds without postMessage
  useEffect(() => {
    if (!isIframe || !target || isResolving) return;

    // Detect user interaction with the iframe (focus shift to p-iframe)
    const handleWindowBlur = () => {
      if (iframeRef.current && document.activeElement === iframeRef.current) {
        hasConfirmedPlaybackRef.current = true;
        onPlaybackStartedRef.current?.();
      }
    };
    window.addEventListener('blur', handleWindowBlur);

    const interval = setInterval(() => {
      const frame = iframeRef.current;
      if (!frame || frame.style.display === 'none') return;
      if (document.visibilityState !== 'visible') return;

      // If genuine postMessage telemetry is active with verified duration, let handleMessage handle progress
      if (progressRef.current.hasVerifiedDuration && progressRef.current.currentTime > 0) {
        return;
      }

      // Requirement 2: An idle iframe must not be treated as confirmed playback.
      // Do not advance or save speculative wall-clock progress while the player is idle.
      if (!hasConfirmedPlaybackRef.current) {
        return;
      }

      const elapsed = Math.floor((Date.now() - iframeWatchStartRef.current) / 1000);
      const activeWatchTime = (iframeBaseOffsetRef.current || 0) + elapsed;
      progressRef.current.currentTime = activeWatchTime;
      setCurrentTime(activeWatchTime);

      if (activeWatchTime >= 5) {
        saveProgress(false, activeWatchTime, target.duration_s || null);
      }
    }, 1000);

    return () => {
      clearInterval(interval);
      window.removeEventListener('blur', handleWindowBlur);
    };
  }, [isIframe, target, isResolving, iframeRef, saveProgress]);

  // Permitted iframe postMessage telemetry listener (Vanilla L6065-6171)
  useEffect(() => {
    if (!isIframe) return;

    const handleMessage = (event: MessageEvent) => {
      try {
        const frame = iframeRef.current;
        if (!frame || frame.style.display === 'none') return;
        if (frame.contentWindow && event.source !== frame.contentWindow) return;

        if (activeIframeOrigin) {
          if (event.origin !== activeIframeOrigin) return;
        } else if (!isPermittedIframeOrigin(event.origin)) {
          return;
        }

        let data = event.data;
        if (typeof data === 'string') {
          try {
            data = JSON.parse(data);
          } catch {
            return;
          }
        }
        if (!data || typeof data !== 'object' || Array.isArray(data)) return;

        const rawCurTime =
          data.currentTime ??
          data.data?.currentTime ??
          data.data?.player_progress ??
          data.value?.seconds ??
          data.value?.currentTime ??
          data.player_progress ??
          data.progress;

        const rawDuration =
          data.duration ??
          data.data?.duration ??
          data.data?.player_duration ??
          data.value?.duration ??
          data.player_duration;

        const cur = Number(rawCurTime);
        const tot = Number(rawDuration);

        const hasValidCur = Number.isFinite(cur) && cur >= 0 && cur <= 172800;
        // Vanilla L6100: Duration must be >= 300s to filter out ad frames
        const hasValidDur = Number.isFinite(tot) && tot >= 300 && tot <= 172800;

        if (hasValidCur && hasValidDur && cur > tot + 5) {
          return;
        }

        if (hasValidDur) {
          hasConfirmedPlaybackRef.current = true;
          setDuration(tot);
          setHasVerifiedDuration(true);
          progressRef.current.duration = tot;
          progressRef.current.hasVerifiedDuration = true;
          onPlaybackStartedRef.current?.();
          if (hasValidCur) {
            setCurrentTime(cur);
            progressRef.current.currentTime = cur;
          }
        } else if (hasValidCur) {
          hasConfirmedPlaybackRef.current = true;
          if (progressRef.current.hasVerifiedDuration && cur <= (progressRef.current.duration || 0) + 5) {
            setCurrentTime(cur);
            progressRef.current.currentTime = cur;
          }
        }

        const evt = (
          data.event ||
          data.type ||
          data.action ||
          data.status ||
          data.data?.player_status ||
          ''
        )
          .toString()
          .toLowerCase();

        const isEndedMsg =
          evt === 'ended' ||
          evt === 'complete' ||
          evt === 'completed' ||
          evt === 'playback_ended' ||
          evt === 'finish' ||
          (data.data && String(data.data.player_status).toLowerCase() === 'ended');

        if (isEndedMsg && (progressRef.current.duration || 0) >= 300) {
          setIsEnded(true);
          progressRef.current.isEnded = true;
          saveProgress(true, cur, hasValidDur ? tot : progressRef.current.duration);
          onEnded?.();
        } else if (progressRef.current.hasVerifiedDuration && progressRef.current.currentTime >= 5) {
          saveProgress(false, progressRef.current.currentTime, progressRef.current.duration);
        }
      } catch {}
    };

    window.addEventListener('message', handleMessage);
    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, [isIframe, activeIframeOrigin, iframeRef, saveProgress, onEnded]);

  // Page visibility change / pagehide / beforeunload save (Vanilla L3773-3777)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        saveProgress(true);
      }
    };
    const handlePageHide = () => {
      saveProgress(true);
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('pagehide', handlePageHide);
    window.addEventListener('beforeunload', handlePageHide);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('pagehide', handlePageHide);
      window.removeEventListener('beforeunload', handlePageHide);
      saveProgress(true);
    };
  }, [saveProgress]);

  return {
    currentTime,
    duration,
    hasVerifiedDuration,
    isEnded,
    saveProgress,
    flushProgress,
  };
}
