import React from 'react';
import { UserRound, Shield, Bookmark, Lock, House, Settings, Info, LogOut } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useRouter } from '../../router';
import { useWatchlist } from '../watchlist';

export const ProfilePage: React.FC = () => {
  const { authenticated, username, role, logout } = useAuth();
  const { navigate } = useRouter();
  const { itemCount: watchlistCount } = useWatchlist();

  if (!authenticated) {
    return (
      <div className="profile-unauth-container">
        <div className="profile-card-glass">
          <div className="profile-avatar-placeholder"><UserRound size={48} strokeWidth={1.5} /></div>
          <h2>Guest Viewer</h2>
          <p className="profile-desc">
            You are currently browsing CineMyMovies in guest mode. Sign in to access your personal account, saved watchlist, and full streaming resolution.
          </p>
          <a href="/login" className="btn btn-primary btn-large">
            Sign In to CineMyMovies
          </a>
        </div>
      </div>
    );
  }

  const roleLabel = role === 'admin' ? 'Administrator' : 'Streaming Member';

  return (
    <div className="profile-page-container">
      <div className="profile-card-glass">
        {/* Profile Header */}
        <div className="profile-header-area">
          <div className="profile-avatar-circle">
            {username ? username.charAt(0).toUpperCase() : 'U'}
          </div>
          <div className="profile-title-block">
            <h1 className="profile-username">{username}</h1>
            <div className="profile-role-badge-row">
              <span className={`role-badge ${role || 'viewer'}`}>{roleLabel}</span>
              <span className="session-status-badge">Active Session</span>
            </div>
          </div>
        </div>

        {/* Account Details Box */}
        <div className="profile-details-grid">
          <div className="profile-detail-card">
            <span className="detail-icon"><UserRound size={18} strokeWidth={1.5} /></span>
            <div className="detail-info">
              <span className="detail-label">Username</span>
              <span className="detail-value">{username}</span>
            </div>
          </div>

          <div className="profile-detail-card">
            <span className="detail-icon"><Shield size={18} strokeWidth={1.5} /></span>
            <div className="detail-info">
              <span className="detail-label">Account Privilege</span>
              <span className="detail-value">{roleLabel}</span>
            </div>
          </div>

          <div className="profile-detail-card">
            <span className="detail-icon"><Bookmark size={18} strokeWidth={1.5} /></span>
            <div className="detail-info">
              <span className="detail-label">My Saved List</span>
              <span className="detail-value">{watchlistCount} Saved Titles</span>
            </div>
          </div>

          <div className="profile-detail-card">
            <span className="detail-icon"><Lock size={18} strokeWidth={1.5} /></span>
            <div className="detail-info">
              <span className="detail-label">Security Protocol</span>
              <span className="detail-value">Server-side Encrypted Session</span>
            </div>
          </div>
        </div>

        {/* Quick Platform Shortcuts */}
        <div className="profile-shortcuts-section">
          <h3 className="section-heading">Quick Shortcuts</h3>
          <div className="shortcuts-row">
            <button
              type="button"
              className="btn btn-secondary shortcut-btn"
              onClick={() => navigate('/my-list')}
            >
              <Bookmark size={15} strokeWidth={1.5} /> <span>My List ({watchlistCount})</span>
            </button>
            <button
              type="button"
              className="btn btn-secondary shortcut-btn"
              onClick={() => navigate('/')}
            >
              <House size={15} strokeWidth={1.5} /> <span>Home & Continue Watching</span>
            </button>
            {role === 'admin' && (
              <button
                type="button"
                className="btn btn-admin shortcut-btn"
                onClick={() => navigate('/admin')}
              >
                <Settings size={15} strokeWidth={1.5} /> <span>Open Admin Console</span>
              </button>
            )}
          </div>
        </div>

        {/* Administrator Policy Notice */}
        <div className="profile-policy-notice">
          <span className="policy-icon"><Info size={16} strokeWidth={1.5} /></span>
          <p className="policy-text">
            <strong>Account Policy:</strong> Credential changes and member provisioning are managed centrally by the system administrator. Self-serve email or password changes are disabled for viewer accounts.
          </p>
        </div>

        {/* Sign Out Action */}
        <div className="profile-signout-row">
          <button
            type="button"
            className="btn btn-auth-logout-large"
            onClick={logout}
          >
            <LogOut size={16} strokeWidth={1.5} /> <span>Sign Out of CineMyMovies</span>
          </button>
        </div>
      </div>
    </div>
  );
};

