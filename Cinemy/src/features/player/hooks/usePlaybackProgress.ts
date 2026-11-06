import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../../../context/AuthContext';
import {
  resolveContinueWatchingKey,
  saveContinueWatchingRecord,
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
  const progressRef = useRef({
    currentTime: target?.resumeTime || 0,
    duration: null as number | null,
    hasVerifiedDuration: false,
    isEnded: false,
  });

  // Keep progressRef in sync with React state
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

      if (cur >= 5) {
        const prevContentId = buildContentId(prev);
        const isSeries = Boolean(prev.isSeries);
        const validDuration =
          Number.isFinite(dur) && (dur ?? 0) > 0 ? Math.floor(dur!) : null;

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
          isCompleted: ended || (validDuration ? (cur / validDuration) >= 0.9 : false),
          updatedAt: Date.now(),
        });
      }

      // Reset telemetry for new target
      setCurrentTime(target.resumeTime || 0);
      setDuration(null);
      setHasVerifiedDuration(false);
      setIsEnded(false);
      lastSaveTimeRef.current = 0;
      progressRef.current = {
        currentTime: target.resumeTime || 0,
        duration: null,
        hasVerifiedDuration: false,
        isEnded: false,
      };
    }
    prevTargetRef.current = target;
  }, [target, scopedKey]);

  // Unified save progress callback with explicit value overrides to avoid React closure lag
  const saveProgress = useCallback(
    (force: boolean = false, overrideCur?: number, overrideDur?: number | null) => {
      if (!target) return;

      const cur = overrideCur !== undefined ? overrideCur : progressRef.current.currentTime;
      const dur = overrideDur !== undefined ? overrideDur : progressRef.current.duration;
      const verified = progressRef.current.hasVerifiedDuration;
      const ended = progressRef.current.isEnded;

      // Do not save negligible initial playback (< 5s) unless already marked ended
      if (cur < 5 && !ended) return;

      // Throttle non-forced saves to roughly every 10 seconds
      if (!force && !ended && lastSaveTimeRef.current > 0 && Math.abs(cur - lastSaveTimeRef.current) < 9.5) {
        return;
      }
      lastSaveTimeRef.current = cur;

      const contentId = buildContentId(target);
      const isSeries = Boolean(target.isSeries);
      const validDuration =
        Number.isFinite(dur) && (dur ?? 0) > 0 ? Math.floor(dur!) : null;

      const progressPct =
        validDuration && validDuration > 0
          ? Math.min(100, Math.round((cur / validDuration) * 100))
          : 0;

      // Mark completed if >= 90% or ended
      const isCompleted = ended || (validDuration ? (cur / validDuration) >= 0.9 : false);

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
        hasVerifiedDuration: Boolean((verified || Boolean(validDuration)) && validDuration),
        progressPct,
        isCompleted,
        updatedAt: Date.now(),
      });
    },
    [target, scopedKey]
  );

  const flushProgress = useCallback(() => {
    saveProgress(true);
  }, [saveProgress]);

  // Native HTML5 Video telemetry listeners
  useEffect(() => {
    if (isIframe) return;
    const video = videoRef.current;
    if (!video) return;

    const handleTimeUpdate = () => {
      if (isNaN(video.currentTime)) return;
      const cur = video.currentTime;
      const dur = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : null;

      if (cur > 0 && !video.paused) {
        onPlaybackStartedRef.current?.();
      }

      // Update progressRef synchronously
      progressRef.current.currentTime = cur;
      if (dur) {
        progressRef.current.duration = dur;
        progressRef.current.hasVerifiedDuration = true;
      }

      setCurrentTime(cur);
      saveProgress(false, cur, dur);
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
    video.addEventListener('durationchange', handleDurationChange);
    video.addEventListener('loadedmetadata', handleDurationChange);
    video.addEventListener('pause', handlePause);
    video.addEventListener('ended', handleEnded);

    return () => {
      video.removeEventListener('timeupdate', handleTimeUpdate);
      video.removeEventListener('durationchange', handleDurationChange);
      video.removeEventListener('loadedmetadata', handleDurationChange);
      video.removeEventListener('pause', handlePause);
      video.removeEventListener('ended', handleEnded);
    };
  }, [isIframe, videoRef, streamSrc, isResolving, saveProgress, onEnded]);

  // Permitted iframe postMessage telemetry listener (e.g. Server 2 VIP VidSrc)
  useEffect(() => {
    if (!isIframe) return;

    const handleMessage = (event: MessageEvent) => {
      try {
        const frame = iframeRef.current;
        if (!frame) return;

        // Origin validation: strictly check activeIframeOrigin or approved embed hostnames
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
        if (!data || typeof data !== 'object') return;

        // Parse duration and time from standard embed telemetry protocols
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
        const hasValidDur = Number.isFinite(tot) && tot > 0 && tot <= 172800;

        if (hasValidDur) {
          setDuration(tot);
          setHasVerifiedDuration(true);
          progressRef.current.duration = tot;
          progressRef.current.hasVerifiedDuration = true;
          onPlaybackStartedRef.current?.();
        }

        if (hasValidCur) {
          setCurrentTime(cur);
          progressRef.current.currentTime = cur;
          if (cur > 0) {
            onPlaybackStartedRef.current?.();
          }
        }

        // Check ended signals
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

        if (isEndedMsg) {
          setIsEnded(true);
          progressRef.current.isEnded = true;
          saveProgress(true, cur, hasValidDur ? tot : progressRef.current.duration);
          onEnded?.();
        } else if (hasValidCur && cur >= 5) {
          saveProgress(false, cur, hasValidDur ? tot : progressRef.current.duration);
        }
      } catch {}
    };

    window.addEventListener('message', handleMessage);
    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, [isIframe, activeIframeOrigin, iframeRef, saveProgress, onEnded]);

  // Page visibility change / unload save
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        saveProgress(true);
      }
    };

    const handleBeforeUnload = () => {
      saveProgress(true);
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('beforeunload', handleBeforeUnload);
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
