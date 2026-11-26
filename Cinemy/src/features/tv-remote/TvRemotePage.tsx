import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Tv,
  Smartphone,
  KeyRound,
  RefreshCw,
  Unlink,
  CheckCircle2,
  Wifi,
  ArrowLeft,
  Play,
  Pause,
  RotateCcw,
  RotateCw,
  SkipBack,
  SkipForward,
  VolumeX,
  Volume2,
  Search,
  House,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useRouter } from '../../router';
import { searchTitles } from '../../api/catalogue';
import { SearchItem } from '../../types/catalogue';
import { completeTvPairing, getTvDevices, revokeTvController } from './api';
import {
  readActiveRemoteTvId,
  readStoredControllers,
  removeStoredController,
  saveActiveRemoteTvId,
  saveStoredController,
} from './storage';
import { StoredControllerAuth, TvDeviceSummary } from './types';
import { useTvRemote } from './TvRemoteContext';
import { TvTouchpad } from './TvTouchpad';
import './tv-remote.css';

function defaultPhoneName(): string {
  if (typeof navigator === 'undefined') return 'Mobile Remote';
  const ua = navigator.userAgent || '';
  if (/iPhone/i.test(ua)) return 'iPhone Remote';
  if (/iPad/i.test(ua)) return 'iPad Remote';
  if (/Android/i.test(ua)) return 'Android Remote';
  return 'Mobile Remote';
}

function formatClock(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return '0:00';
  const total = Math.floor(sec);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export const TvRemotePage: React.FC = () => {
  const { authenticated } = useAuth();
  const { search, navigate } = useRouter();
  const {
    phoneWsStatus,
    tvOnline,
    tvState,
    lastAckMessage,
    refreshPhoneControllers,
    selectActiveTv,
    reconnectPhone,
    sendCommand,
    playOnTv,
  } = useTvRemote();

  const [devices, setDevices] = useState<TvDeviceSummary[]>([]);
  const [storedControllers, setStoredControllers] = useState<Record<string, StoredControllerAuth>>(() =>
    readStoredControllers()
  );
  const [activeTvId, setActiveTvId] = useState<string | null>(() => readActiveRemoteTvId());
  const [codeInput, setCodeInput] = useState<string>('');
  const [phoneName, setPhoneName] = useState<string>(defaultPhoneName);
  const [loadingDevices, setLoadingDevices] = useState<boolean>(false);
  const [pairingBusy, setPairingBusy] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Search-to-TV state (Phase 3)
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [searchResults, setSearchResults] = useState<SearchItem[]>([]);
  const [searching, setSearching] = useState<boolean>(false);

  const qrHandledRef = useRef<string>('');

  const refreshDevices = useCallback(async () => {
    setLoadingDevices(true);
    try {
      const res = await getTvDevices();
      setDevices(res.devices || []);
    } catch (err: any) {
      setError(err?.message || 'Unable to load TVs.');
    } finally {
      setLoadingDevices(false);
    }
  }, []);

  // Phase 5: Initial load + periodic automatic discovery refresh while on TV Remote page
  useEffect(() => {
    if (!authenticated) return;
    void refreshDevices();
    const timer = setInterval(() => {
      void refreshDevices();
    }, 10000);
    return () => clearInterval(timer);
  }, [authenticated, refreshDevices]);

  // Sync local storedControllers if revoked remotely via WebSocket
  useEffect(() => {
    if (phoneWsStatus === 'revoked') {
      setStoredControllers(readStoredControllers());
      setActiveTvId(readActiveRemoteTvId());
      setError('This phone was disconnected from the TV. Pair again to reconnect.');
    }
  }, [phoneWsStatus]);

  const finishPairing = useCallback(
    async (payload: { pairing_id?: string; pairing_token?: string; code?: string }) => {
      setPairingBusy(true);
      setError(null);
      setNotice(null);
      try {
        const res = await completeTvPairing({
          ...payload,
          phone_name: phoneName.trim() || defaultPhoneName(),
        });
        const auth: StoredControllerAuth = {
          tvId: res.tv_id,
          tvName: res.tv_name,
          controllerId: res.controller_id,
          controlToken: res.control_token,
          phoneName: res.phone_name,
          role: res.role,
          pairedAt: res.created_at,
        };
        saveStoredController(auth);
        setStoredControllers(readStoredControllers());
        setActiveTvId(res.tv_id);
        refreshPhoneControllers();
        setCodeInput('');
        setNotice(`Connected to ${res.tv_name}.`);
        await refreshDevices();
      } catch (err: any) {
        const detail = err?.details?.detail;
        const msg =
          (typeof detail === 'object' && detail?.message) ||
          err?.message ||
          'Pairing failed. Please check the code and try again.';
        setError(msg);
      } finally {
        setPairingBusy(false);
      }
    },
    [phoneName, refreshDevices, refreshPhoneControllers]
  );

  // Auto-complete deep-link pairing when opened via URL (/remote?pid=...&t=...)
  useEffect(() => {
    if (!authenticated || !search) return;
    const params = new URLSearchParams(search);
    const pid = params.get('pid');
    const tok = params.get('t');
    const key = `${pid || ''}:${tok || ''}`;
    if (pid && tok && qrHandledRef.current !== key) {
      qrHandledRef.current = key;
      void finishPairing({ pairing_id: pid, pairing_token: tok }).finally(() => {
        navigate('/remote', { replace: true, scroll: false });
      });
    }
  }, [authenticated, search, finishPairing, navigate]);

  const handleCodeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const digits = codeInput.replace(/\D/g, '');
    if (digits.length !== 6) {
      setError('Enter the 6-digit pairing code displayed on your TV.');
      return;
    }
    await finishPairing({ code: digits });
  };

  const handleSelectTv = (tvId: string) => {
    if (storedControllers[tvId]) {
      saveActiveRemoteTvId(tvId);
      setActiveTvId(tvId);
      selectActiveTv(tvId);
      setNotice(`Switched remote target to ${storedControllers[tvId].tvName}.`);
    } else {
      setNotice('Scan the QR code or enter the 6-digit code shown on this TV to authorize pairing.');
    }
  };

  const handleDisconnect = async (tvId: string) => {
    const auth = storedControllers[tvId];
    setError(null);
    try {
      if (auth) {
        await revokeTvController(tvId, auth.controllerId);
      }
    } catch {
      // Remove local token even if already revoked server-side
    } finally {
      removeStoredController(tvId);
      setStoredControllers(readStoredControllers());
      const nextActive = readActiveRemoteTvId();
      setActiveTvId(nextActive);
      refreshPhoneControllers();
      setNotice('Disconnected from TV. Any active TV playback will continue uninterrupted.');
      void refreshDevices();
    }
  };

  const handleSearchToTv = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = searchQuery.trim();
    if (!q) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    try {
      const res = await searchTitles(q, 8);
      setSearchResults(res.items || []);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  const handleLaunchItemOnTv = (item: SearchItem) => {
    const sent = playOnTv({
      id: item.id,
      title: item.title,
      year: item.year,
      poster: item.poster,
      isSeries: Boolean(item.is_series),
      season: item.is_series ? 1 : undefined,
      episode: item.is_series ? 1 : undefined,
      source: item.source || 'yomovies',
    });
    if (sent) {
      setNotice(`Sending "${item.title}" to TV...`);
    } else {
      setError('TV disconnected. Tap Reconnect and try again.');
    }
  };

  if (!authenticated) {
    return (
      <div className="tv-page-container">
        <div className="tv-card">
          <h2>Sign In Required</h2>
          <p className="tv-muted">Sign in to your CINEMY account to connect and control your TV.</p>
          <a href="/login" className="btn btn-primary">Sign In</a>
        </div>
      </div>
    );
  }

  const activeAuth = activeTvId ? storedControllers[activeTvId] : null;
  const activeDevice = activeTvId ? devices.find((d) => d.tv_id === activeTvId) : null;
  const activeTvName = activeDevice?.name || activeAuth?.tvName || 'Connected TV';
  const isDisconnected = Boolean(activeAuth && (phoneWsStatus === 'disconnected' || !tvOnline));
  const pos = tvState?.currentPosition || 0;
  const dur = tvState?.duration || 0;
  const isPlaying = Boolean(tvState?.isPlaying || tvState?.status === 'PLAYING');

  return (
    <div className="tv-page-container">
      <div className="tv-top-bar">
        <button type="button" className="btn btn-secondary" onClick={() => navigate('/')}>
          <ArrowLeft size={16} /> <span>Home</span>
        </button>
        <button type="button" className="btn btn-secondary" onClick={refreshDevices} disabled={loadingDevices}>
          <RefreshCw size={15} /> <span>Refresh TVs</span>
        </button>
      </div>

      <div className="tv-grid-two">
        {/* Left: Connected Remote Controller + Nearby TVs */}
        <div className="tv-card">
          <div className="tv-card-header">
            <Smartphone size={22} />
            <div>
              <h1 className="tv-heading">TV Remote</h1>
              <p className="tv-muted">Control playback on your TV. Your TV owns playback independently of your phone.</p>
            </div>
          </div>

          {error && <div className="tv-alert tv-alert-error" role="alert">{error}</div>}
          {notice && <div className="tv-alert tv-alert-success">{notice}</div>}

          {!activeAuth && (
            <div className="tv-empty-box" data-testid="no-tv-connected-banner" style={{ marginBottom: '16px' }}>
              <p style={{ fontWeight: 600, margin: '0 0 6px' }}>No TV connected</p>
              <p className="tv-muted-sm" style={{ marginBottom: '12px' }}>
                Select a nearby TV below or enter the 6-digit code displayed on your TV.
              </p>
              <button
                type="button"
                className="btn btn-primary tv-btn-sm"
                onClick={() => {
                  const el = document.getElementById('tv-code-input');
                  el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  el?.focus();
                }}
              >
                Connect a TV
              </button>
            </div>
          )}

          {activeAuth && (
            <>
              <div className="tv-active-banner" data-testid="active-tv-banner">
                <div className="tv-list-info">
                  <div className="tv-list-title">
                    <CheckCircle2 size={16} className={isDisconnected ? 'tv-status-offline' : 'tv-dot-online'} />
                    <strong>{activeTvName}</strong>
                    <span className="tv-role-pill">
                      {phoneWsStatus === 'connected' && tvOnline
                        ? 'Connected'
                        : phoneWsStatus === 'connecting'
                        ? 'Connecting...'
                        : 'TV disconnected'}
                    </span>
                  </div>
                  <span className="tv-muted-sm">
                    Paired as {activeAuth.phoneName} ({activeAuth.role})
                  </span>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {isDisconnected && (
                    <button
                      type="button"
                      className="btn btn-primary tv-btn-sm"
                      onClick={reconnectPhone}
                    >
                      Reconnect
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-secondary tv-btn-sm"
                    onClick={() => handleDisconnect(activeAuth.tvId)}
                  >
                    <Unlink size={14} /> <span>Disconnect</span>
                  </button>
                </div>
              </div>

              {/* Phase 2 & 4: Authoritative TV Now Playing + Transport Controls */}
              <div className="tv-now-playing" data-testid="tv-now-playing" style={{ marginTop: '14px' }}>
                <div className="tv-now-playing-header">
                  <div>
                    <h3 className="tv-now-playing-title">
                      {tvState?.currentTitle || 'Nothing playing on TV'}
                    </h3>
                    {tvState?.currentEpisode && (
                      <p className="tv-now-playing-ep">{tvState.currentEpisode}</p>
                    )}
                  </div>
                  <span className="tv-role-pill" data-testid="tv-playback-status">
                    {tvState?.status || 'IDLE'}
                  </span>
                </div>

                {dur > 0 && (
                  <div className="tv-seek-wrap">
                    <input
                      type="range"
                      min={0}
                      max={Math.floor(dur)}
                      value={Math.min(Math.floor(pos), Math.floor(dur))}
                      onChange={(e) => sendCommand({ command: 'SEEK_TO', position: Number(e.target.value) })}
                      className="tv-seek-slider"
                      aria-label="Seek TV playback position"
                    />
                    <div className="tv-seek-times">
                      <span>{formatClock(pos)}</span>
                      <span>{formatClock(dur)}</span>
                    </div>
                  </div>
                )}

                <div className="tv-transport-row">
                  <button
                    type="button"
                    className="btn btn-secondary tv-btn-sm"
                    onClick={() => sendCommand({ command: 'SEEK_BACKWARD', seconds: 10 })}
                    aria-label="Rewind 10 seconds"
                  >
                    <RotateCcw size={15} /> <span>10s</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => sendCommand({ command: isPlaying ? 'PAUSE' : 'PLAY' })}
                    aria-label={isPlaying ? 'Pause TV' : 'Play TV'}
                  >
                    {isPlaying ? <Pause size={18} /> : <Play size={18} />}
                    <span>{isPlaying ? 'Pause' : 'Play'}</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary tv-btn-sm"
                    onClick={() => sendCommand({ command: 'SEEK_FORWARD', seconds: 30 })}
                    aria-label="Forward 30 seconds"
                  >
                    <span>30s</span> <RotateCw size={15} />
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary tv-btn-sm"
                    onClick={() => sendCommand({ command: 'MUTE_TOGGLE' })}
                    aria-label="Toggle TV mute"
                  >
                    {tvState?.muted ? <VolumeX size={15} /> : <Volume2 size={15} />}
                  </button>
                </div>

                {tvState?.isSeries && (
                  <div className="tv-transport-row" style={{ marginTop: '10px' }}>
                    <button
                      type="button"
                      className="btn btn-secondary tv-btn-sm"
                      onClick={() => sendCommand({ command: 'PREVIOUS_EPISODE' })}
                    >
                      <SkipBack size={14} /> <span>Prev Episode</span>
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary tv-btn-sm"
                      onClick={() => sendCommand({ command: 'NEXT_EPISODE' })}
                    >
                      <span>Next Episode</span> <SkipForward size={14} />
                    </button>
                  </div>
                )}

                {lastAckMessage && (
                  <p className="tv-muted-sm" style={{ textAlign: 'center', marginTop: '10px' }}>
                    {lastAckMessage}
                  </p>
                )}
              </div>

              {/* TV Touchpad (Primary Navigation Surface) + Compact Secondary Back / Home */}
              <TvTouchpad
                onCommand={(command) => sendCommand({ command })}
                disabled={phoneWsStatus !== 'connected'}
              />

              <div className="tv-secondary-nav-row" aria-label="Secondary TV actions">
                <button
                  type="button"
                  className="btn btn-secondary tv-secondary-nav-btn"
                  onClick={() => sendCommand({ command: 'BACK' })}
                >
                  <ArrowLeft size={14} /> <span>Back</span>
                </button>
                <button
                  type="button"
                  className="btn btn-secondary tv-secondary-nav-btn"
                  onClick={() => sendCommand({ command: 'HOME' })}
                >
                  <House size={14} /> <span>Home</span>
                </button>
              </div>

              {/* Phase 3: Search CINEMY & Play directly on TV */}
              <div className="tv-now-playing">
                <form onSubmit={handleSearchToTv} className="tv-name-row">
                  <input
                    type="text"
                    className="tv-input"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search CINEMY to Play on TV..."
                    aria-label="Search CINEMY to Play on TV"
                  />
                  <button type="submit" className="btn btn-primary" disabled={searching}>
                    <Search size={15} /> <span>{searching ? '...' : 'Search'}</span>
                  </button>
                </form>

                {searchResults.length > 0 && (
                  <ul className="tv-search-results">
                    {searchResults.map((item) => (
                      <li key={item.id} className="tv-list-item">
                        <div className="tv-list-info">
                          <span className="tv-list-title">{item.title}</span>
                          <span className="tv-muted-sm">
                            {item.year || ''} • {item.is_series ? 'Series' : 'Movie'}
                          </span>
                        </div>
                        <button
                          type="button"
                          className="btn btn-primary tv-btn-sm"
                          onClick={() => handleLaunchItemOnTv(item)}
                        >
                          <Tv size={14} /> <span>Play on TV</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}

          <h2 className="tv-section-label">Nearby &amp; Available TVs</h2>
          {devices.length === 0 ? (
            <div className="tv-empty-box">
              <p className="tv-muted">No CINEMY TVs registered on this account yet.</p>
              <p className="tv-muted-sm">On your TV browser, open Profile → Connect Phone to display a 6-digit code.</p>
            </div>
          ) : (
            <ul className="tv-list">
              {devices.map((dev) => {
                const isPaired = Boolean(storedControllers[dev.tv_id]);
                const isSelected = activeTvId === dev.tv_id;
                return (
                  <li
                    key={dev.tv_id}
                    className={`tv-list-item ${isSelected ? 'selected' : ''}`}
                  >
                    <div className="tv-list-info">
                      <div className="tv-list-title">
                        <Tv size={16} />
                        <span>{dev.name}</span>
                        {dev.nearby && (
                          <span className="tv-nearby-pill">
                            <Wifi size={12} /> Nearby
                          </span>
                        )}
                      </div>
                      <span className="tv-muted-sm">
                        <span className={dev.online ? 'tv-status-online' : 'tv-status-offline'}>
                          ● {dev.online ? (isPaired ? 'Connected' : 'Available') : 'Offline'}
                        </span>
                      </span>
                    </div>
                    <button
                      type="button"
                      className="btn btn-secondary tv-btn-sm"
                      onClick={() => handleSelectTv(dev.tv_id)}
                    >
                      {isSelected ? 'Selected' : isPaired ? 'Select' : 'Pair'}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Right: Pair via 6-Digit Code */}
        <div className="tv-card">
          <div className="tv-card-header">
            <KeyRound size={22} />
            <div>
              <h2 className="tv-subheading">Pair a TV</h2>
              <p className="tv-muted">Enter the 6-digit code shown on your TV.</p>
            </div>
          </div>

          <form className="tv-code-form" onSubmit={handleCodeSubmit}>
            <label htmlFor="tv-code-input" className="tv-label">
              <KeyRound size={14} style={{ verticalAlign: 'middle', marginRight: 6 }} />
              Enter 6-Digit TV Code
            </label>
            <input
              id="tv-code-input"
              type="text"
              inputMode="numeric"
              className="tv-input tv-code-input"
              value={codeInput}
              onChange={(e) => setCodeInput(e.target.value)}
              placeholder="583 214"
              maxLength={9}
            />

            <label htmlFor="phone-name-input" className="tv-label" style={{ marginTop: '12px' }}>
              This Phone Name
            </label>
            <input
              id="phone-name-input"
              type="text"
              className="tv-input"
              value={phoneName}
              onChange={(e) => setPhoneName(e.target.value)}
              maxLength={60}
              placeholder="Living Room Phone"
            />

            <button
              type="submit"
              className="btn btn-primary"
              disabled={pairingBusy || codeInput.replace(/\D/g, '').length !== 6}
              style={{ marginTop: '14px', width: '100%' }}
            >
              {pairingBusy ? 'Connecting...' : 'Connect to TV'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};
