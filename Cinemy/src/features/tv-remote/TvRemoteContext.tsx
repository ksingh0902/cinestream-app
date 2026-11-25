import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useRef,
  useCallback,
  ReactNode,
} from 'react';
import { useAuth } from '../../context/AuthContext';
import {
  clearStoredTvIdentity,
  DeviceRole,
  readActiveRemoteTvId,
  readStoredControllers,
  readStoredTvIdentity,
  removeStoredController,
  resolveDeviceRole,
  saveActiveRemoteTvId,
} from './storage';
import {
  RemoteCommandPayload,
  StoredControllerAuth,
  StoredTvIdentity,
  TvPlaybackState,
} from './types';

export type PhoneWsStatus = 'disconnected' | 'connecting' | 'connected' | 'revoked';
export type TvWsStatus = 'disconnected' | 'connecting' | 'connected';

type PlayerCommandHandler = (cmd: RemoteCommandPayload) => void;
type MediaLaunchHandler = (media: NonNullable<RemoteCommandPayload['media']>) => void;
type NavigationCommandHandler = (cmd: RemoteCommandPayload) => void;

export interface TvRemoteContextType {
  // Authoritative device role ('tv' vs 'phone')
  deviceRole: DeviceRole;

  // TV side
  tvIdentity: StoredTvIdentity | null;
  tvWsStatus: TvWsStatus;
  connectedControllerCount: number;
  refreshTvIdentity: () => void;
  publishTvPlaybackState: (state: TvPlaybackState, immediate?: boolean) => void;
  registerPlayerCommandHandler: (handler: PlayerCommandHandler | null) => void;
  registerMediaLaunchHandler: (handler: MediaLaunchHandler | null) => void;
  registerNavigationHandler: (handler: NavigationCommandHandler | null) => void;

  // Phone side
  controllers: Record<string, StoredControllerAuth>;
  activeController: StoredControllerAuth | null;
  phoneWsStatus: PhoneWsStatus;
  tvOnline: boolean;
  tvState: TvPlaybackState | null;
  lastAckMessage: string | null;
  refreshPhoneControllers: () => void;
  selectActiveTv: (tvId: string | null) => void;
  reconnectPhone: () => void;
  sendCommand: (payload: RemoteCommandPayload) => boolean;
  playOnTv: (media: NonNullable<RemoteCommandPayload['media']>) => boolean;
}

const NOOP_CONTEXT: TvRemoteContextType = {
  deviceRole: 'phone',
  tvIdentity: null,
  tvWsStatus: 'disconnected',
  connectedControllerCount: 0,
  refreshTvIdentity: () => {},
  publishTvPlaybackState: () => {},
  registerPlayerCommandHandler: () => {},
  registerMediaLaunchHandler: () => {},
  registerNavigationHandler: () => {},
  controllers: {},
  activeController: null,
  phoneWsStatus: 'disconnected',
  tvOnline: false,
  tvState: null,
  lastAckMessage: null,
  refreshPhoneControllers: () => {},
  selectActiveTv: () => {},
  reconnectPhone: () => {},
  sendCommand: () => false,
  playOnTv: () => false,
};

const TvRemoteContext = createContext<TvRemoteContextType>(NOOP_CONTEXT);

function buildWsUrl(params: Record<string, string>): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const qs = new URLSearchParams(params).toString();
  return `${proto}//${window.location.host}/api/tv/ws?${qs}`;
}

export const TvRemoteProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { authenticated } = useAuth();

  // TV state
  const [tvIdentity, setTvIdentity] = useState<StoredTvIdentity | null>(() => readStoredTvIdentity());
  const [tvWsStatus, setTvWsStatus] = useState<TvWsStatus>('disconnected');
  const [connectedControllerCount, setConnectedControllerCount] = useState<number>(0);

  // Phone state
  const [controllers, setControllers] = useState<Record<string, StoredControllerAuth>>(() =>
    readStoredControllers()
  );
  const [activeTvId, setActiveTvId] = useState<string | null>(() => readActiveRemoteTvId());
  const [phoneWsStatus, setPhoneWsStatus] = useState<PhoneWsStatus>('disconnected');
  const [tvOnline, setTvOnline] = useState<boolean>(false);
  const [tvState, setTvState] = useState<TvPlaybackState | null>(null);
  const [lastAckMessage, setLastAckMessage] = useState<string | null>(null);
  const [phoneReconnectNonce, setPhoneReconnectNonce] = useState<number>(0);

  // Socket & handler refs
  const tvWsRef = useRef<WebSocket | null>(null);
  const phoneWsRef = useRef<WebSocket | null>(null);
  const playerHandlerRef = useRef<PlayerCommandHandler | null>(null);
  const mediaLaunchHandlerRef = useRef<MediaLaunchHandler | null>(null);
  const navHandlerRef = useRef<NavigationCommandHandler | null>(null);
  const lastTvStateSentAtRef = useRef<number>(0);
  const lastTvStateStatusRef = useRef<string>('');
  const latestTvStateRef = useRef<TvPlaybackState | null>(null);

  const activeController = activeTvId ? controllers[activeTvId] || null : null;
  const deviceRole: DeviceRole = resolveDeviceRole(
    tvIdentity,
    activeController || controllers
  );

  // Automatically remove any stale TV identity on a browser that already has a paired phone controller
  useEffect(() => {
    if (
      deviceRole === 'phone' &&
      tvIdentity?.tvId &&
      (activeController || Object.keys(controllers).length > 0)
    ) {
      clearStoredTvIdentity();
      setTvIdentity(null);
    }
  }, [deviceRole, tvIdentity, activeController, controllers]);

  const refreshTvIdentity = useCallback(() => {
    setTvIdentity(readStoredTvIdentity());
  }, []);

  const refreshPhoneControllers = useCallback(() => {
    const next = readStoredControllers();
    setControllers(next);
    const active = readActiveRemoteTvId();
    setActiveTvId(active && next[active] ? active : Object.keys(next)[0] || null);
    setTvIdentity(readStoredTvIdentity());
  }, []);

  const selectActiveTv = useCallback((tvId: string | null) => {
    saveActiveRemoteTvId(tvId);
    setActiveTvId(tvId);
    setTvState(null);
    setTvOnline(false);
  }, []);

  const reconnectPhone = useCallback(() => {
    setPhoneReconnectNonce((n) => n + 1);
  }, []);

  const registerPlayerCommandHandler = useCallback((handler: PlayerCommandHandler | null) => {
    playerHandlerRef.current = handler;
  }, []);

  const registerMediaLaunchHandler = useCallback((handler: MediaLaunchHandler | null) => {
    mediaLaunchHandlerRef.current = handler;
  }, []);

  const registerNavigationHandler = useCallback((handler: NavigationCommandHandler | null) => {
    navHandlerRef.current = handler;
  }, []);

  // TV -> Server throttled authoritative playback state publisher
  const publishTvPlaybackState = useCallback((state: TvPlaybackState, immediate = false) => {
    latestTvStateRef.current = state;
    const ws = tvWsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    const now = Date.now();
    const statusChanged = state.status !== lastTvStateStatusRef.current;
    if (!immediate && !statusChanged && now - lastTvStateSentAtRef.current < 2200) {
      return;
    }

    lastTvStateSentAtRef.current = now;
    lastTvStateStatusRef.current = state.status;
    try {
      ws.send(JSON.stringify({ type: 'state', state }));
    } catch {
      // Never interrupt TV playback on telemetry send error
    }
  }, []);

  // TV WebSocket lifecycle: resilient reconnect; NEVER pauses/stops TV playback on disconnect
  // Guarded by deviceRole === 'tv' so a phone browser never opens a phantom role=tv WebSocket
  useEffect(() => {
    if (!authenticated || deviceRole !== 'tv' || !tvIdentity?.tvId || !tvIdentity?.deviceSecret) {
      setTvWsStatus('disconnected');
      return;
    }
    if (typeof WebSocket === 'undefined') return;

    let cancelled = false;
    let attempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let pingTimer: ReturnType<typeof setInterval> | null = null;

    const connectTv = () => {
      if (cancelled) return;
      setTvWsStatus('connecting');
      const url = buildWsUrl({
        role: 'tv',
        tv_id: tvIdentity.tvId,
        device_secret: tvIdentity.deviceSecret,
      });

      const ws = new WebSocket(url);
      tvWsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) return;
        attempt = 0;
        setTvWsStatus('connected');
        // Push latest authoritative state immediately so any waiting phone syncs
        if (latestTvStateRef.current) {
          try {
            ws.send(JSON.stringify({ type: 'state', state: latestTvStateRef.current }));
          } catch {}
        }
        pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try {
              ws.send(JSON.stringify({ type: 'ping' }));
            } catch {}
          }
        }, 25000);
      };

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(String(evt.data || '{}'));
          if (msg.type === 'connected' && Array.isArray(msg.connected_controllers)) {
            setConnectedControllerCount(msg.connected_controllers.length);
          } else if (msg.type === 'controller_connected') {
            setConnectedControllerCount((c) => c + 1);
            // Send fresh authoritative TV state to newly connected/reconnected phone
            if (latestTvStateRef.current && ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'state', state: latestTvStateRef.current }));
            }
          } else if (msg.type === 'controller_disconnected') {
            // CRITICAL: Phone disconnected -> ONLY update count, NEVER pause or stop TV playback!
            setConnectedControllerCount((c) => Math.max(0, c - 1));
          } else if (msg.type === 'command') {
            const cmdPayload: RemoteCommandPayload = {
              command: msg.command,
              seconds: msg.seconds,
              position: msg.position,
              volume: msg.volume,
              media: msg.media,
            };
            if (cmdPayload.command === 'LOAD_MEDIA' && cmdPayload.media) {
              mediaLaunchHandlerRef.current?.(cmdPayload.media);
            } else if (
              cmdPayload.command === 'NAVIGATE_UP' ||
              cmdPayload.command === 'NAVIGATE_DOWN' ||
              cmdPayload.command === 'NAVIGATE_LEFT' ||
              cmdPayload.command === 'NAVIGATE_RIGHT' ||
              cmdPayload.command === 'SELECT' ||
              cmdPayload.command === 'HOME'
            ) {
              navHandlerRef.current?.(cmdPayload);
            } else if (cmdPayload.command === 'BACK') {
              if (playerHandlerRef.current) {
                playerHandlerRef.current(cmdPayload);
              } else {
                navHandlerRef.current?.(cmdPayload);
              }
            } else {
              playerHandlerRef.current?.(cmdPayload);
            }
          }
        } catch {
          // Ignore malformed frames
        }
      };

      ws.onclose = (ev) => {
        if (pingTimer) clearInterval(pingTimer);
        if (tvWsRef.current === ws) tvWsRef.current = null;
        if (cancelled) return;
        setTvWsStatus('disconnected');
        if (ev.code === 4401 || ev.code === 4403) return;
        const delay = Math.min(10000, 1500 * Math.pow(2, attempt++));
        reconnectTimer = setTimeout(connectTv, delay);
      };

      ws.onerror = () => {
        // onclose handles reconnect
      };
    };

    connectTv();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (pingTimer) clearInterval(pingTimer);
      if (tvWsRef.current) {
        try {
          tvWsRef.current.close();
        } catch {}
        tvWsRef.current = null;
      }
    };
  }, [authenticated, deviceRole, tvIdentity]);

  // Phone WebSocket lifecycle: reconnects on network return / wake from phone call
  useEffect(() => {
    if (!authenticated || !activeController?.tvId || !activeController?.controlToken) {
      setPhoneWsStatus('disconnected');
      setTvOnline(false);
      return;
    }
    if (typeof WebSocket === 'undefined') return;

    let cancelled = false;
    let attempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let pingTimer: ReturnType<typeof setInterval> | null = null;

    const connectPhone = () => {
      if (cancelled) return;
      setPhoneWsStatus('connecting');
      const url = buildWsUrl({
        role: 'phone',
        tv_id: activeController.tvId,
        controller_id: activeController.controllerId,
        control_token: activeController.controlToken,
      });

      const ws = new WebSocket(url);
      phoneWsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) return;
        attempt = 0;
        setPhoneWsStatus('connected');
        pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try {
              ws.send(JSON.stringify({ type: 'ping' }));
            } catch {}
          }
        }, 25000);
      };

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(String(evt.data || '{}'));
          if (msg.type === 'connected') {
            setTvOnline(Boolean(msg.tv_online));
            if (msg.state) setTvState(msg.state);
          } else if (msg.type === 'tv_status') {
            setTvOnline(Boolean(msg.online));
            if (msg.state) setTvState(msg.state);
          } else if (msg.type === 'state' && msg.state) {
            setTvOnline(true);
            setTvState(msg.state);
          } else if (msg.type === 'ack') {
            setLastAckMessage(
              msg.delivered
                ? `${msg.command} sent to TV`
                : `TV is offline — could not deliver ${msg.command}`
            );
          } else if (msg.type === 'revoked') {
            setPhoneWsStatus('revoked');
            removeStoredController(activeController.tvId);
            setControllers(readStoredControllers());
            setActiveTvId(readActiveRemoteTvId());
          }
        } catch {
          // Ignore malformed frames
        }
      };

      ws.onclose = (ev) => {
        if (pingTimer) clearInterval(pingTimer);
        if (phoneWsRef.current === ws) phoneWsRef.current = null;
        if (cancelled) return;
        if (ev.code === 4403) {
          setPhoneWsStatus('revoked');
          removeStoredController(activeController.tvId);
          setControllers(readStoredControllers());
          setActiveTvId(readActiveRemoteTvId());
          return;
        }
        setPhoneWsStatus('disconnected');
        const delay = Math.min(10000, 1500 * Math.pow(2, attempt++));
        reconnectTimer = setTimeout(connectPhone, delay);
      };

      ws.onerror = () => {
        // onclose handles reconnect
      };
    };

    const handleVisibilityOrOnline = () => {
      if (document.visibilityState === 'visible' && (!phoneWsRef.current || phoneWsRef.current.readyState !== WebSocket.OPEN)) {
        if (reconnectTimer) clearTimeout(reconnectTimer);
        attempt = 0;
        connectPhone();
      }
    };

    connectPhone();
    window.addEventListener('online', handleVisibilityOrOnline);
    document.addEventListener('visibilitychange', handleVisibilityOrOnline);

    return () => {
      cancelled = true;
      window.removeEventListener('online', handleVisibilityOrOnline);
      document.removeEventListener('visibilitychange', handleVisibilityOrOnline);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (pingTimer) clearInterval(pingTimer);
      if (phoneWsRef.current) {
        try {
          phoneWsRef.current.close();
        } catch {}
        phoneWsRef.current = null;
      }
    };
  }, [authenticated, activeController, phoneReconnectNonce]);

  const sendCommand = useCallback((payload: RemoteCommandPayload): boolean => {
    const ws = phoneWsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setLastAckMessage('TV disconnected — tap Reconnect.');
      return false;
    }
    try {
      ws.send(JSON.stringify({ type: 'command', ...payload }));
      return true;
    } catch {
      return false;
    }
  }, []);

  const playOnTv = useCallback(
    (media: NonNullable<RemoteCommandPayload['media']>): boolean => {
      return sendCommand({ command: 'LOAD_MEDIA', media });
    },
    [sendCommand]
  );

  return (
    <TvRemoteContext.Provider
      value={{
        deviceRole,
        tvIdentity,
        tvWsStatus,
        connectedControllerCount,
        refreshTvIdentity,
        publishTvPlaybackState,
        registerPlayerCommandHandler,
        registerMediaLaunchHandler,
        registerNavigationHandler,
        controllers,
        activeController,
        phoneWsStatus,
        tvOnline,
        tvState,
        lastAckMessage,
        refreshPhoneControllers,
        selectActiveTv,
        reconnectPhone,
        sendCommand,
        playOnTv,
      }}
    >
      {children}
    </TvRemoteContext.Provider>
  );
};

export function useTvRemote(): TvRemoteContextType {
  return useContext(TvRemoteContext);
}
