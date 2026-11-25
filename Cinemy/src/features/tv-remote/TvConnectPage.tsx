import React, { useState, useEffect, useCallback } from 'react';
import { Tv, Smartphone, RefreshCw, Unlink, CheckCircle2, ArrowLeft } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useRouter } from '../../router';
import {
  registerTvDevice,
  startTvPairing,
  heartbeatTvDevice,
  revokeTvController,
} from './api';
import { readStoredTvIdentity, saveStoredTvIdentity } from './storage';
import { StartPairingResponse, TvControllerSummary } from './types';
import { QrCodeSvg } from './QrCodeSvg';
import { useTvRemote } from './TvRemoteContext';
import './tv-remote.css';

export const TvConnectPage: React.FC = () => {
  const { authenticated } = useAuth();
  const { navigate } = useRouter();
  const { refreshTvIdentity, tvWsStatus } = useTvRemote();

  const [tvId, setTvId] = useState<string>('');
  const [tvName, setTvName] = useState<string>(() => readStoredTvIdentity()?.name || 'Living Room TV');
  const [editingName, setEditingName] = useState<string>(() => readStoredTvIdentity()?.name || 'Living Room TV');
  const [pairing, setPairing] = useState<StartPairingResponse | null>(null);
  const [controllers, setControllers] = useState<TvControllerSummary[]>([]);
  const [secondsLeft, setSecondsLeft] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const initTvAndPairing = useCallback(async (customName?: string) => {
    setLoading(true);
    setError(null);
    setStatusMsg(null);
    try {
      const stored = readStoredTvIdentity();
      const desiredName = (customName || stored?.name || 'Living Room TV').trim() || 'Living Room TV';
      const reg = await registerTvDevice({
        tv_id: stored?.tvId,
        device_secret: stored?.deviceSecret,
        name: desiredName,
      });

      const finalSecret = reg.device_secret || stored?.deviceSecret || '';
      saveStoredTvIdentity({
        tvId: reg.tv_id,
        name: reg.name,
        deviceSecret: finalSecret,
      });
      refreshTvIdentity();
      setTvId(reg.tv_id);
      setTvName(reg.name);
      setEditingName(reg.name);
      setControllers(reg.controllers || []);

      const pairRes = await startTvPairing(reg.tv_id);
      setPairing(pairRes);
      setSecondsLeft(Math.max(0, pairRes.expires_at - Math.floor(Date.now() / 1000)));
    } catch (err: any) {
      setError(err?.message || 'Unable to initialize TV pairing session.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authenticated) return;
    void initTvAndPairing();
  }, [authenticated, initTvAndPairing]);

  // Countdown timer for pairing code expiry
  useEffect(() => {
    if (!pairing) return;
    const tick = setInterval(() => {
      const remaining = Math.max(0, pairing.expires_at - Math.floor(Date.now() / 1000));
      setSecondsLeft(remaining);
    }, 1000);
    return () => clearInterval(tick);
  }, [pairing]);

  // Heartbeat while on Connect Phone screen so newly paired phones appear automatically
  useEffect(() => {
    if (!authenticated || !tvId) return;
    const interval = setInterval(() => {
      heartbeatTvDevice(tvId)
        .then((res) => {
          if (res?.controllers) {
            setControllers(res.controllers);
          }
        })
        .catch(() => {});
    }, 4000);
    return () => clearInterval(interval);
  }, [authenticated, tvId]);

  const handleRefreshCode = async () => {
    if (!tvId) {
      await initTvAndPairing(editingName);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const pairRes = await startTvPairing(tvId);
      setPairing(pairRes);
      setSecondsLeft(Math.max(0, pairRes.expires_at - Math.floor(Date.now() / 1000)));
    } catch (err: any) {
      setError(err?.message || 'Failed to refresh pairing code.');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveName = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = editingName.trim();
    if (!cleaned) return;
    setLoading(true);
    setError(null);
    try {
      const stored = readStoredTvIdentity();
      const reg = await registerTvDevice({
        tv_id: tvId || stored?.tvId,
        device_secret: stored?.deviceSecret,
        name: cleaned,
      });
      saveStoredTvIdentity({
        tvId: reg.tv_id,
        name: reg.name,
        deviceSecret: reg.device_secret || stored?.deviceSecret || '',
      });
      setTvName(reg.name);
      setStatusMsg(`TV renamed to "${reg.name}".`);
    } catch (err: any) {
      setError(err?.message || 'Unable to rename TV.');
    } finally {
      setLoading(false);
    }
  };

  const handleRevoke = async (controllerId?: string) => {
    if (!tvId) return;
    setError(null);
    try {
      await revokeTvController(tvId, controllerId);
      setControllers((prev) =>
        controllerId ? prev.filter((c) => c.controller_id !== controllerId) : []
      );
      setStatusMsg(controllerId ? 'Phone disconnected and revoked.' : 'All phones disconnected.');
    } catch (err: any) {
      setError(err?.message || 'Failed to disconnect phone.');
    }
  };

  if (!authenticated) {
    return (
      <div className="tv-page-container">
        <div className="tv-card">
          <h2>Sign In Required</h2>
          <p className="tv-muted">Sign in to your CINEMY account on this TV before pairing a phone remote.</p>
          <a href="/login" className="btn btn-primary">Sign In</a>
        </div>
      </div>
    );
  }

  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  const qrValue = pairing ? `${origin}${pairing.qr_path}` : '';
  const isExpired = Boolean(pairing && secondsLeft <= 0);

  return (
    <div className="tv-page-container">
      <div className="tv-top-bar">
        <button type="button" className="btn btn-secondary" onClick={() => navigate('/profile')}>
          <ArrowLeft size={16} /> <span>Back</span>
        </button>
        <div className="tv-id-pill">
          <Tv size={15} />
          <span>{tvName}</span>
          {tvId && <code className="tv-id-code">{tvId}</code>}
          <span className={tvWsStatus === 'connected' ? 'tv-status-online' : 'tv-status-offline'}>
            ● {tvWsStatus === 'connected' ? 'Online' : tvWsStatus === 'connecting' ? 'Connecting' : 'Offline'}
          </span>
        </div>
      </div>

      <div className="tv-grid-two">
        {/* Left: QR + 6-Digit Pairing Card */}
        <div className="tv-card">
          <div className="tv-card-header">
            <Tv size={22} />
            <div>
              <h1 className="tv-heading">Connect Phone</h1>
              <p className="tv-muted">Scan the QR code or enter the 6-digit code in CINEMY TV Remote on your phone.</p>
            </div>
          </div>

          {error && <div className="tv-alert tv-alert-error" role="alert">{error}</div>}
          {statusMsg && <div className="tv-alert tv-alert-success">{statusMsg}</div>}

          <div className="tv-qr-panel">
            {pairing ? (
              <>
                <div className={`tv-qr-frame ${isExpired ? 'expired' : ''}`}>
                  <QrCodeSvg value={qrValue} size={210} label={`QR code to pair ${tvName}`} />
                </div>

                <div className="tv-code-block">
                  <span className="tv-code-label">Or enter code on your phone</span>
                  <div className="tv-code-digits" data-testid="tv-pairing-code">
                    {pairing.display_code}
                  </div>
                  <span className="tv-code-expiry">
                    {isExpired
                      ? 'Code expired — click Refresh Code'
                      : `Expires in ${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, '0')} • Waiting for connection...`}
                  </span>
                </div>
              </>
            ) : (
              <p className="tv-muted">{loading ? 'Generating pairing code...' : 'No active pairing code.'}</p>
            )}

            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleRefreshCode}
              disabled={loading}
            >
              <RefreshCw size={15} /> <span>Refresh Code</span>
            </button>
          </div>

          <form className="tv-name-form" onSubmit={handleSaveName}>
            <label htmlFor="tv-name-input" className="tv-label">TV Name</label>
            <div className="tv-name-row">
              <input
                id="tv-name-input"
                type="text"
                className="tv-input"
                value={editingName}
                onChange={(e) => setEditingName(e.target.value)}
                maxLength={60}
                placeholder="Living Room TV"
              />
              <button type="submit" className="btn btn-secondary" disabled={loading}>
                Save
              </button>
            </div>
          </form>
        </div>

        {/* Right: Connected / Authorized Phones */}
        <div className="tv-card">
          <div className="tv-card-header">
            <Smartphone size={22} />
            <div>
              <h2 className="tv-subheading">Authorized Phones</h2>
              <p className="tv-muted">
                Playback stays owned by this TV even if your phone locks, receives a call, or disconnects.
              </p>
            </div>
          </div>

          {controllers.length === 0 ? (
            <div className="tv-empty-box">
              <p className="tv-muted">No phones connected yet.</p>
              <p className="tv-muted-sm">Open CINEMY → TV Remote on your phone and scan the QR code or enter the 6-digit code.</p>
            </div>
          ) : (
            <>
              <ul className="tv-list">
                {controllers.map((ctrl) => (
                  <li key={ctrl.controller_id} className="tv-list-item">
                    <div className="tv-list-info">
                      <div className="tv-list-title">
                        <CheckCircle2 size={16} className="tv-dot-online" />
                        <span>{ctrl.phone_name}</span>
                        <span className="tv-role-pill">{ctrl.role}</span>
                      </div>
                      <span className="tv-muted-sm">Authorized remote</span>
                    </div>
                    <button
                      type="button"
                      className="btn btn-secondary tv-btn-sm"
                      onClick={() => handleRevoke(ctrl.controller_id)}
                    >
                      <Unlink size={14} /> <span>Disconnect</span>
                    </button>
                  </li>
                ))}
              </ul>
              {controllers.length > 1 && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => handleRevoke()}
                  style={{ marginTop: '12px' }}
                >
                  Disconnect All Phones
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
