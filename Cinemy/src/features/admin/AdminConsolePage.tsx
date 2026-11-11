import React, { useState, useEffect } from 'react';
import { ShieldAlert, Settings, RefreshCw, Check, AlertTriangle, Activity, BarChart3, Sparkles, KeyRound, ArrowLeft, Sliders } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useRouter } from '../../router';
import { getHomepagePreferences, updateHomepagePreferences } from '../../api/catalogue';
import { HomepagePreferences } from '../../types/catalogue';
import {
  fetchStats,
  fetchSyncStatus,
  fetchHealth,
  triggerCatalogSync,
  changeViewerPassword,
  signOutAllViewers,
  CatalogueStats,
  SyncStatus,
  SystemHealth,
} from './adminService';
import { LoadingSpinner } from '../../components/common/LoadingSpinner';

export const AdminConsolePage: React.FC = () => {
  const { role, authenticated } = useAuth();
  const { navigate } = useRouter();

  const [stats, setStats] = useState<CatalogueStats | null>(null);
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionNotice, setActionNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Homepage discovery preferences
  const [prefs, setPrefs] = useState<HomepagePreferences>({
    recently_added_enabled: true,
    recently_upgraded_enabled: true,
    recently_added_window_months: 3,
    recently_upgraded_window_months: 3,
    default_sort: 'recent',
    allowed_qualities: ['4K', '1080p', '720p', 'HD', 'WEB-DL', 'BluRay'],
  });
  const [isSavingPrefs, setIsSavingPrefs] = useState<boolean>(false);

  // Form states
  const [currentAdminPw, setCurrentAdminPw] = useState<string>('');
  const [newViewerPw, setNewViewerPw] = useState<string>('');
  const [isSubmittingPw, setIsSubmittingPw] = useState<boolean>(false);
  const [isTriggeringSync, setIsTriggeringSync] = useState<boolean>(false);
  const [isRevokingViewers, setIsRevokingViewers] = useState<boolean>(false);

  // Security gate: non-admin accounts are rejected
  if (!authenticated || role !== 'admin') {
    return (
      <div className="admin-forbidden-container">
        <div className="forbidden-card-glass">
          <div className="forbidden-icon"><ShieldAlert size={48} strokeWidth={1.5} /></div>
          <h2>403 Forbidden: Administrator Access Required</h2>
          <p>
            You are signed in as a viewer or unauthenticated member. The administrator console is strictly restricted to system administrators.
          </p>
          <button type="button" className="btn btn-primary" onClick={() => navigate('/')}>
            <ArrowLeft size={16} strokeWidth={1.5} /> <span>Return to Home</span>
          </button>
        </div>
      </div>
    );
  }

  const loadDashboardData = async () => {
    setLoading(true);
    try {
      const [statsRes, syncRes, healthRes, prefsRes] = await Promise.all([
        fetchStats().catch(() => null),
        fetchSyncStatus().catch(() => null),
        fetchHealth().catch(() => null),
        getHomepagePreferences().catch(() => null),
      ]);
      setStats(statsRes);
      setSyncStatus(syncRes);
      setHealth(healthRes);
      if (prefsRes) setPrefs(prefsRes);
    } finally {
      setLoading(false);
    }
  };

  const handleSavePreferences = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSavingPrefs(true);
    setActionNotice(null);
    try {
      const res = await updateHomepagePreferences(prefs);
      if (res && res.ok) {
        setPrefs(res.preferences);
        setActionNotice({ type: 'success', text: 'Homepage discovery preferences updated successfully.' });
      } else {
        setActionNotice({ type: 'error', text: 'Failed to update preferences.' });
      }
    } catch (err: any) {
      setActionNotice({ type: 'error', text: err.message || 'Error updating homepage preferences.' });
    } finally {
      setIsSavingPrefs(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, []);

  const handleTriggerSync = async () => {
    setIsTriggeringSync(true);
    setActionNotice(null);
    try {
      const res = await triggerCatalogSync();
      setActionNotice({ type: 'success', text: res.message || 'Catalogue synchronization initiated successfully.' });
      const newSync = await fetchSyncStatus().catch(() => null);
      if (newSync) setSyncStatus(newSync);
    } catch (err: any) {
      setActionNotice({ type: 'error', text: err.message || 'Failed to trigger catalogue sync.' });
    } finally {
      setIsTriggeringSync(false);
    }
  };

  const handleChangeViewerPw = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentAdminPw || !newViewerPw) {
      setActionNotice({ type: 'error', text: 'Please fill in both current administrator password and new viewer password.' });
      return;
    }
    setIsSubmittingPw(true);
    setActionNotice(null);
    try {
      const res = await changeViewerPassword(currentAdminPw, newViewerPw);
      if (res.success) {
        setActionNotice({ type: 'success', text: res.message });
        setNewViewerPw('');
        setCurrentAdminPw('');
      } else {
        setActionNotice({ type: 'error', text: res.message });
      }
    } catch (err: any) {
      setActionNotice({ type: 'error', text: err.message || 'Password update failed.' });
    } finally {
      setIsSubmittingPw(false);
    }
  };

  const handleSignOutViewers = async () => {
    if (!currentAdminPw) {
      setActionNotice({ type: 'error', text: 'Enter current administrator password to authorize session revocation.' });
      return;
    }
    if (!window.confirm('Are you sure you want to sign out all active viewer devices immediately?')) {
      return;
    }
    setIsRevokingViewers(true);
    setActionNotice(null);
    try {
      const res = await signOutAllViewers(currentAdminPw);
      if (res.success) {
        setActionNotice({ type: 'success', text: res.message });
      } else {
        setActionNotice({ type: 'error', text: res.message });
      }
    } catch (err: any) {
      setActionNotice({ type: 'error', text: err.message || 'Session revocation failed.' });
    } finally {
      setIsRevokingViewers(false);
    }
  };

  return (
    <div className="admin-console-container">
      <div className="page-header-row">
        <div>
          <h1 className="page-title" style={{ display: "flex", alignItems: "center", gap: 8 }}><Settings size={24} strokeWidth={1.5} /> Administrator Control Console</h1>
          <p className="page-subtitle">Platform health, catalogue statistics, and viewer security governance</p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={loadDashboardData}>
          <RefreshCw size={14} strokeWidth={1.5} /> <span>Refresh Metrics</span>
        </button>
      </div>

      {actionNotice && (
        <div className={`action-notice-box ${actionNotice.type}`}>
          {actionNotice.type === 'success' ? <Check size={14} strokeWidth={1.5} /> : <AlertTriangle size={14} strokeWidth={1.5} />} <span>{actionNotice.text}</span>
        </div>
      )}

      {loading ? (
        <div className="admin-loading-box">
          <LoadingSpinner label="Querying administrative endpoints..." size="lg" />
        </div>
      ) : (
        <div className="admin-grid-layout">
          {/* Card 1: System Health */}
          <div className="admin-card">
            <h3 className="card-header" style={{ display: "flex", alignItems: "center", gap: 6 }}><Activity size={16} strokeWidth={1.5} /> System Health & Database</h3>
            <div className="stat-metric-row">
              <span className="metric-label">Catalogue Database:</span>
              <span className="metric-value status-good">{health?.catalogue || 'Connected (SQLite)'}</span>
            </div>
            <div className="stat-metric-row">
              <span className="metric-label">Backend Liveness:</span>
              <span className="metric-value status-good">{health?.ok ? 'Online & Healthy' : 'Degraded'}</span>
            </div>
            <div className="stat-metric-row">
              <span className="metric-label">Server Time:</span>
              <span className="metric-value">{health?.time ? new Date(health.time * 1000).toLocaleTimeString() : '—'}</span>
            </div>
          </div>

          {/* Card 2: Catalogue Statistics */}
          <div className="admin-card">
            <h3 className="card-header" style={{ display: "flex", alignItems: "center", gap: 6 }}><BarChart3 size={16} strokeWidth={1.5} /> Catalogue Coverage</h3>
            <div className="stat-metric-row">
              <span className="metric-label">Total Titles:</span>
              <span className="metric-value highlight">{stats?.total_titles || '—'}</span>
            </div>
            <div className="stat-metric-row">
              <span className="metric-label">Movies:</span>
              <span className="metric-value">{stats?.total_movies || '—'}</span>
            </div>
            <div className="stat-metric-row">
              <span className="metric-label">Series:</span>
              <span className="metric-value">{stats?.total_series || '—'}</span>
            </div>
          </div>

          {/* Card 3: Scraper Sync Controls */}
          <div className="admin-card">
            <h3 className="card-header" style={{ display: "flex", alignItems: "center", gap: 6 }}><RefreshCw size={16} strokeWidth={1.5} /> Scraper & Catalogue Sync</h3>
            <div className="stat-metric-row">
              <span className="metric-label">Sync Status:</span>
              <span className="metric-value">{syncStatus?.status || 'Idle'}</span>
            </div>
            <div className="stat-metric-row">
              <span className="metric-label">Last Synchronization:</span>
              <span className="metric-value">{syncStatus?.last_sync || 'Recently'}</span>
            </div>
            <div className="admin-btn-action-row" style={{ marginTop: '16px' }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleTriggerSync}
                disabled={isTriggeringSync}
              >
                {isTriggeringSync ? 'Starting Sync...' : (<><Sparkles size={14} strokeWidth={1.5} /> <span>Trigger Catalogue Sync</span></>)}
              </button>
            </div>
          </div>

          {/* Card 4: Viewer Governance & Password Management */}
          <div className="admin-card span-full">
            <h3 className="card-header" style={{ display: "flex", alignItems: "center", gap: 6 }}><KeyRound size={16} strokeWidth={1.5} /> Viewer Account Governance</h3>
            <p className="card-desc">
              Change the shared viewer password or instantly invalidate all active viewer sessions across all devices.
            </p>

            <form onSubmit={handleChangeViewerPw} className="admin-form-row">
              <div className="form-group">
                <label className="form-label">Current Admin Password (Authorization)</label>
                <input
                  type="password"
                  className="form-input"
                  placeholder="Enter administrator password"
                  value={currentAdminPw}
                  onChange={(e) => setCurrentAdminPw(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">New Viewer Password</label>
                <input
                  type="password"
                  className="form-input"
                  placeholder="Enter new viewer password"
                  value={newViewerPw}
                  onChange={(e) => setNewViewerPw(e.target.value)}
                />
              </div>

              <div className="form-actions-inline">
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={isSubmittingPw}
                >
                  {isSubmittingPw ? 'Updating...' : 'Update Viewer Password'}
                </button>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={handleSignOutViewers}
                  disabled={isRevokingViewers}
                >
                  {isRevokingViewers ? 'Revoking...' : 'Revoke All Viewer Sessions'}
                </button>
              </div>
            </form>
          </div>

          {/* Card 5: Homepage Discovery Preferences */}
          <div className="admin-card span-full">
            <h3 className="card-header" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Sliders size={16} strokeWidth={1.5} /> Homepage Discovery Sections Configuration
            </h3>
            <p className="card-desc">
              Configure visibility, time windows, and default catalogue behavior for the homepage discovery sections.
            </p>

            <form onSubmit={handleSavePreferences} className="admin-prefs-grid">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px', marginBottom: '16px' }}>
                {/* Toggle Recently Added */}
                <div className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: 500 }}>
                    <input
                      type="checkbox"
                      checked={prefs.recently_added_enabled}
                      onChange={(e) => setPrefs((prev) => ({ ...prev, recently_added_enabled: e.target.checked }))}
                    />
                    <span>Enable "Recently Added" Section</span>
                  </label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '12px', color: 'var(--dim)' }}>Recency Window:</span>
                    <select
                      className="form-input"
                      style={{ padding: '4px 8px', fontSize: '13px', width: 'auto' }}
                      value={prefs.recently_added_window_months}
                      onChange={(e) => setPrefs((prev) => ({ ...prev, recently_added_window_months: Number(e.target.value) }))}
                    >
                      <option value={1}>1 Month</option>
                      <option value={2}>2 Months</option>
                      <option value={3}>3 Months (Default)</option>
                      <option value={6}>6 Months</option>
                      <option value={12}>12 Months</option>
                    </select>
                  </div>
                </div>

                {/* Toggle Recently Upgraded */}
                <div className="form-group" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: 500 }}>
                    <input
                      type="checkbox"
                      checked={prefs.recently_upgraded_enabled}
                      onChange={(e) => setPrefs((prev) => ({ ...prev, recently_upgraded_enabled: e.target.checked }))}
                    />
                    <span>Enable "Recently Upgraded" Section</span>
                  </label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '12px', color: 'var(--dim)' }}>Recency Window:</span>
                    <select
                      className="form-input"
                      style={{ padding: '4px 8px', fontSize: '13px', width: 'auto' }}
                      value={prefs.recently_upgraded_window_months}
                      onChange={(e) => setPrefs((prev) => ({ ...prev, recently_upgraded_window_months: Number(e.target.value) }))}
                    >
                      <option value={1}>1 Month</option>
                      <option value={2}>2 Months</option>
                      <option value={3}>3 Months (Default)</option>
                      <option value={6}>6 Months</option>
                      <option value={12}>12 Months</option>
                    </select>
                  </div>
                </div>

                {/* Default Sorting */}
                <div className="form-group">
                  <label className="form-label">Default Catalogue Sorting</label>
                  <select
                    className="form-input"
                    value={prefs.default_sort}
                    onChange={(e) => setPrefs((prev) => ({ ...prev, default_sort: e.target.value }))}
                  >
                    <option value="recent">Default (Recommended / Recent)</option>
                    <option value="first_added">Newest Added (First Discovered)</option>
                    <option value="recently_upgraded">Recently Upgraded Quality</option>
                    <option value="year">Release Year (Newest First)</option>
                    <option value="quality">Highest Available Quality</option>
                    <option value="title">Alphabetical (A–Z)</option>
                  </select>
                </div>
              </div>

              <div className="form-actions-inline">
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={isSavingPrefs}
                >
                  {isSavingPrefs ? 'Saving Preferences...' : 'Save Homepage Discovery Preferences'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

