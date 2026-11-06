import { useEffect, useRef } from 'react';
import type HlsType from 'hls.js';

interface UseHlsPlayerOptions {
  videoRef: React.RefObject<HTMLVideoElement>;
  src: string | null;
  autoPlay?: boolean;
  initialSeekTime?: number;
  onSelfHeal?: () => void;
  onFatalError?: (errorMessage: string) => void;
  onReady?: () => void;
}

// Module-level cached promise for HLS.js module to prevent duplicate network downloads
let hlsModulePromise: Promise<typeof import('hls.js')> | null = null;

function loadHlsModule(): Promise<typeof import('hls.js')> {
  if (!hlsModulePromise) {
    hlsModulePromise = import('hls.js').catch((err) => {
      // Clear cache on failure so future attempts can retry
      hlsModulePromise = null;
      throw err;
    });
  }
  return hlsModulePromise;
}

export function useHlsPlayer({
  videoRef,
  src,
  autoPlay = true,
  initialSeekTime = 0,
  onSelfHeal,
  onFatalError,
  onReady,
}: UseHlsPlayerOptions) {
  const hlsRef = useRef<HlsType | null>(null);
  const seekAppliedRef = useRef<boolean>(false);

  // Keep callback and config refs stable across parent component re-renders
  const onSelfHealRef = useRef(onSelfHeal);
  onSelfHealRef.current = onSelfHeal;
  const onFatalErrorRef = useRef(onFatalError);
  onFatalErrorRef.current = onFatalError;
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;
  const initialSeekTimeRef = useRef(initialSeekTime);
  initialSeekTimeRef.current = initialSeekTime;

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) return;

    seekAppliedRef.current = false;
    let isDisposed = false;

    // Teardown previous Hls instance
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }

    const applyInitialSeek = () => {
      if (seekAppliedRef.current) return;
      const seekTarget = initialSeekTimeRef.current;
      if (seekTarget && seekTarget > 3) {
        seekAppliedRef.current = true;
        try {
          video.currentTime = Math.max(0, seekTarget - 3);
        } catch {}
      }
    };

    // 1. If native Safari / Apple HLS is supported and preferred, use it without loading HLS.js
    const canPlayNativeHls = video.canPlayType('application/vnd.apple.mpegurl');

    // Helper for native HLS playback
    const attachNativeHls = () => {
      video.src = src;

      const handleLoadedMetadata = () => {
        if (isDisposed) return;
        applyInitialSeek();
        onReadyRef.current?.();
        if (autoPlay) {
          video.play().catch(() => {});
        }
      };

      const handleError = () => {
        if (isDisposed) return;
        onSelfHealRef.current?.();
      };

      video.addEventListener('loadedmetadata', handleLoadedMetadata, { once: true });
      video.addEventListener('error', handleError, { once: true });

      return () => {
        video.removeEventListener('loadedmetadata', handleLoadedMetadata);
        video.removeEventListener('error', handleError);
      };
    };

    let cleanupNative: (() => void) | undefined;

    // 2. Load HLS.js dynamically on-demand when stream requires MediaSource playback
    loadHlsModule()
      .then((hlsModule) => {
        if (isDisposed) return;

        const Hls = hlsModule.default || hlsModule;

        if (Hls.isSupported()) {
          const seekTarget = initialSeekTimeRef.current;
          const startPos = seekTarget && seekTarget > 3 ? Math.max(0, seekTarget - 3) : -1;

          const hls = new Hls({
            startPosition: startPos,
            maxBufferLength: 30,
            maxMaxBufferLength: 60,
            backBufferLength: 30,
            enableWorker: true,
            lowLatencyMode: false,
            nudgeMaxRetry: 5,
            nudgeOffset: 0.2,
            xhrSetup: (xhr) => {
              xhr.withCredentials = true;
            },
          });

          hlsRef.current = hls;

          hls.loadSource(src);
          hls.attachMedia(video);

          hls.on(Hls.Events.MANIFEST_PARSED, () => {
            if (isDisposed) return;
            applyInitialSeek();
            onReadyRef.current?.();
            if (autoPlay) {
              video.play().catch(() => {});
            }
          });

          hls.on(Hls.Events.LEVEL_LOADED, () => {
            if (isDisposed) return;
            applyInitialSeek();
          });

          hls.on(Hls.Events.ERROR, (_event, data) => {
            if (isDisposed || !data) return;

            // Check HTTP response code for token expiration or resource 404
            const httpStatus =
              data.response?.code ||
              (data.context as any)?.xhr?.status ||
              (data.response as any)?.status;

            if (httpStatus === 401 || httpStatus === 403) {
              console.warn(`HLS HTTP ${httpStatus} error. Attempting token self-healing...`);
              onSelfHealRef.current?.();
              return;
            }

            if (httpStatus === 404 || httpStatus === 410) {
              console.warn(`HLS stream resource unavailable (HTTP ${httpStatus}). Triggering server fallback...`);
              onFatalErrorRef.current?.(`HLS stream unavailable (HTTP ${httpStatus})`);
              return;
            }

            if (!data.fatal) return;

            if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
              console.warn('HLS Network error encountered, restarting load...');
              hls.startLoad();
            } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
              console.warn('HLS Media error encountered, recovering media...');
              hls.recoverMediaError();
            } else {
              console.warn('HLS Fatal unrecoverable error:', data);
              hls.destroy();
              hlsRef.current = null;
              onFatalErrorRef.current?.('Fatal streaming error encountered.');
            }
          });
        } else if (canPlayNativeHls) {
          cleanupNative = attachNativeHls();
        } else {
          onFatalErrorRef.current?.('Your browser does not support HLS video playback.');
        }
      })
      .catch((err) => {
        if (isDisposed) return;
        console.error('Failed to dynamically load HLS streaming engine:', err);
        if (canPlayNativeHls) {
          cleanupNative = attachNativeHls();
        } else {
          onFatalErrorRef.current?.('Failed to load streaming engine. Please check your connection.');
        }
      });

    return () => {
      isDisposed = true;
      if (cleanupNative) {
        cleanupNative();
      }
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
  }, [src, videoRef, autoPlay]);

  return {
    hlsInstance: hlsRef.current,
  };
}
