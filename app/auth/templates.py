from __future__ import annotations

import html
from typing import Any, Dict, Optional


def _esc(val: Any) -> str:
    return html.escape(str(val or ""))


def render_login_page(
    csrf_token: str,
    next_url: str = "/",
    error: Optional[str] = None,
    notice: Optional[str] = None,
) -> str:
    """Render the CineMyMovies dark-themed login interface."""
    next_clean = _esc(next_url)
    csrf_clean = _esc(csrf_token)
    error_html = (
        f'<div class="alert alert-error" role="alert"><span>⚠️</span> {html.escape(error)}</div>'
        if error
        else ""
    )
    notice_html = (
        f'<div class="alert alert-notice" role="alert"><span>ℹ️</span> {html.escape(notice)}</div>'
        if notice
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Login - CineMyMovies</title>
<style>
:root {{
  --bg: #0e0f13;
  --card: #181a20;
  --card-hover: #222630;
  --accent: #ff7b39;
  --accent-glow: rgba(255,123,57,0.25);
  --txt: #ececed;
  --dim: #9aa0aa;
  --border: #262932;
  --error: #ef4444;
  --error-bg: rgba(239, 68, 68, 0.12);
  --notice-bg: rgba(59, 130, 246, 0.12);
  --notice-border: #3b82f6;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--txt);
  font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background-image: radial-gradient(circle at 50% 20%, rgba(255,123,57,0.08), transparent 45%);
}}
.login-card {{
  width: 100%;
  max-width: 400px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 32px 28px;
  box-shadow: 0 16px 40px rgba(0,0,0,0.55);
  backdrop-filter: blur(8px);
}}
.brand {{
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 24px;
  text-decoration: none;
}}
.brand .logo {{
  font-size: 26px;
}}
.brand h1 {{
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.5px;
  color: #fff;
}}
.brand span {{
  color: var(--accent);
}}
.subtitle {{
  text-align: center;
  color: var(--dim);
  font-size: 13px;
  margin-top: -16px;
  margin-bottom: 24px;
}}
.alert {{
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 8px;
}}
.alert-error {{
  background: var(--error-bg);
  border: 1px solid var(--error);
  color: #fca5a5;
}}
.alert-notice {{
  background: var(--notice-bg);
  border: 1px solid var(--notice-border);
  color: #93c5fd;
}}
.field {{
  margin-bottom: 18px;
}}
.field label {{
  display: block;
  font-size: 12.5px;
  font-weight: 600;
  color: #cbd5e1;
  margin-bottom: 7px;
}}
.input-wrap {{
  position: relative;
  display: flex;
  align-items: center;
}}
input[type="text"], input[type="password"] {{
  width: 100%;
  background: #111317;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 11px 14px;
  color: #fff;
  font-size: 14px;
  outline: none;
  transition: border-color .15s, box-shadow .15s;
}}
input[type="text"]:focus, input[type="password"]:focus {{
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}}
.toggle-btn {{
  position: absolute;
  right: 10px;
  background: none;
  border: none;
  color: var(--dim);
  cursor: pointer;
  padding: 6px;
  font-size: 14px;
  line-height: 1;
}}
.toggle-btn:hover {{
  color: #fff;
}}
.btn-submit {{
  width: 100%;
  background: var(--accent);
  border: none;
  border-radius: 8px;
  padding: 12px;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  margin-top: 8px;
  transition: transform .1s, background .15s, box-shadow .15s;
  box-shadow: 0 4px 14px var(--accent-glow);
}}
.btn-submit:hover {{
  background: #ff8e52;
  box-shadow: 0 6px 20px var(--accent-glow);
}}
.btn-submit:active {{
  transform: scale(0.98);
}}
.footer-text {{
  text-align: center;
  color: var(--dim);
  font-size: 12px;
  margin-top: 24px;
}}
</style>
</head>
<body>
<div class="login-card">
  <div class="brand">
    <span class="logo">🎬</span>
    <h1>Cine<span>My</span>Movies</h1>
  </div>
  <p class="subtitle">Private access for authorized members</p>

  {notice_html}
  {error_html}

  <form method="POST" action="/login" autocomplete="off">
    <input type="hidden" name="csrf_token" value="{csrf_clean}">
    <input type="hidden" name="next" value="{next_clean}">

    <div class="field">
      <label for="username">Username</label>
      <input type="text" id="username" name="username" placeholder="viewer or admin" required autofocus spellcheck="false" autocapitalize="none">
    </div>

    <div class="field">
      <label for="password">Password</label>
      <div class="input-wrap">
        <input type="password" id="password" name="password" placeholder="••••••••" required>
        <button type="button" class="toggle-btn" onclick="togglePw()" aria-label="Toggle password visibility">👁️</button>
      </div>
    </div>

    <button type="submit" class="btn-submit">Sign In</button>
  </form>

  <p class="footer-text">Protected with server-managed encrypted sessions</p>
</div>

<script>
function togglePw() {{
  const inp = document.getElementById('password');
  inp.type = inp.type === 'password' ? 'text' : 'password';
}}
</script>
</body>
</html>"""


def render_admin_page(
    csrf_token: str,
    admin_user: Dict[str, Any],
    viewer_user: Dict[str, Any],
    session_counts: Dict[str, int],
    notice: Optional[str] = None,
    error: Optional[str] = None,
) -> str:
    """Render the CineMyMovies dark-themed Administrator Console."""
    csrf_clean = _esc(csrf_token)
    admin_name = _esc(admin_user.get("username", "admin"))
    viewer_name = _esc(viewer_user.get("username", "viewer"))
    viewer_ver = int(viewer_user.get("auth_version", 1))
    admin_ver = int(admin_user.get("auth_version", 1))

    error_html = (
        f'<div class="banner banner-error"><span>⚠️</span> {html.escape(error)}</div>'
        if error
        else ""
    )
    notice_html = (
        f'<div class="banner banner-success"><span>✅</span> {html.escape(notice)}</div>'
        if notice
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Admin Console - CineMyMovies</title>
<style>
:root {{
  --bg: #0e0f13;
  --card: #181a20;
  --card-hover: #222630;
  --accent: #ff7b39;
  --accent-glow: rgba(255,123,57,0.25);
  --txt: #ececed;
  --dim: #9aa0aa;
  --border: #262932;
  --error: #ef4444;
  --error-bg: rgba(239, 68, 68, 0.12);
  --success: #10b981;
  --success-bg: rgba(16, 185, 129, 0.12);
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--txt);
  font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}}
header {{
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  background: #0e0f13f0;
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
}}
.brand {{
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: #fff;
  font-weight: 800;
  font-size: 18px;
}}
.brand span {{ color: var(--accent); }}
.nav-actions {{
  display: flex;
  align-items: center;
  gap: 12px;
}}
.btn-nav {{
  background: #242732;
  border: 1px solid var(--border);
  color: #cbd5e1;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: .15s;
}}
.btn-nav:hover {{
  background: #333846;
  color: #fff;
}}
main {{
  max-width: 960px;
  width: 100%;
  margin: 28px auto;
  padding: 0 20px 40px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}}
.banner {{
  padding: 12px 18px;
  border-radius: 8px;
  font-size: 13.5px;
  display: flex;
  align-items: center;
  gap: 10px;
}}
.banner-error {{
  background: var(--error-bg);
  border: 1px solid var(--error);
  color: #fca5a5;
}}
.banner-success {{
  background: var(--success-bg);
  border: 1px solid var(--success);
  color: #6ee7b7;
}}
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}}
.stat-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
}}
.stat-card .label {{
  color: var(--dim);
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}}
.stat-card .val {{
  font-size: 24px;
  font-weight: 800;
  color: #fff;
  margin-top: 6px;
}}
.stat-card .desc {{
  font-size: 12px;
  color: var(--dim);
  margin-top: 4px;
}}
.panel {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
}}
.panel-header {{
  border-bottom: 1px solid var(--border);
  padding-bottom: 16px;
  margin-bottom: 20px;
}}
.panel-header h2 {{
  font-size: 17px;
  font-weight: 700;
  color: #fff;
  display: flex;
  align-items: center;
  gap: 8px;
}}
.panel-header p {{
  color: var(--dim);
  font-size: 13px;
  margin-top: 4px;
}}
.form-grid {{
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
  max-width: 520px;
}}
.field label {{
  display: block;
  font-size: 12.5px;
  font-weight: 600;
  color: #cbd5e1;
  margin-bottom: 6px;
}}
input[type="text"], input[type="password"] {{
  width: 100%;
  background: #111317;
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 9px 13px;
  color: #fff;
  font-size: 13.5px;
  outline: none;
  transition: border-color .15s;
}}
input[type="text"]:focus, input[type="password"]:focus {{
  border-color: var(--accent);
}}
.btn-primary {{
  background: var(--accent);
  border: none;
  border-radius: 7px;
  padding: 10px 18px;
  color: #fff;
  font-size: 13.5px;
  font-weight: 700;
  cursor: pointer;
  transition: .15s;
  width: fit-content;
}}
.btn-primary:hover {{
  background: #ff8e52;
}}
.btn-danger {{
  background: #dc2626;
  border: none;
  border-radius: 7px;
  padding: 10px 18px;
  color: #fff;
  font-size: 13.5px;
  font-weight: 700;
  cursor: pointer;
  transition: .15s;
  width: fit-content;
}}
.btn-danger:hover {{
  background: #ef4444;
}}
.danger-zone {{
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px dashed var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}}
.danger-info h3 {{
  font-size: 14px;
  color: #fff;
}}
.danger-info p {{
  font-size: 12.5px;
  color: var(--dim);
  margin-top: 2px;
}}
</style>
</head>
<body>
<header>
  <a href="/" class="brand">
    <span>🎬</span> Cine<span>My</span>Movies Admin
  </a>
  <div class="nav-actions">
    <a href="/" class="btn-nav">🎬 Watch Movies</a>
    <form method="POST" action="/logout" style="display:inline">
      <input type="hidden" name="csrf_token" value="{csrf_clean}">
      <button type="submit" class="btn-nav" style="color:#ef4444;border-color:rgba(239,68,68,0.3)">🚪 Sign Out</button>
    </form>
  </div>
</header>

<main>
  {notice_html}
  {error_html}

  <div class="stats-grid">
    <div class="stat-card">
      <div class="label">Shared Viewer Account</div>
      <div class="val">{viewer_name}</div>
      <div class="desc">Active Session Version: v{viewer_ver}</div>
    </div>
    <div class="stat-card">
      <div class="label">Administrator Account</div>
      <div class="val">{admin_name}</div>
      <div class="desc">Active Session Version: v{admin_ver}</div>
    </div>
    <div class="stat-card">
      <div class="label">Active Sessions</div>
      <div class="val">{session_counts.get("total", 0)}</div>
      <div class="desc">{session_counts.get("viewer", 0)} viewers, {session_counts.get("admin", 0)} admin</div>
    </div>
  </div>

  <!-- Panel 1: Shared Viewer Password -->
  <section class="panel">
    <div class="panel-header">
      <h2>👥 Shared Viewer Password & Access</h2>
      <p>Changing the viewer password atomically revokes all existing viewer devices across all platforms.</p>
    </div>
    <form method="POST" action="/api/admin/change-viewer-password" class="form-grid">
      <input type="hidden" name="csrf_token" value="{csrf_clean}">
      <div class="field">
        <label for="new_viewer_password">New Shared Viewer Password</label>
        <input type="password" id="new_viewer_password" name="new_viewer_password" placeholder="At least 6 characters" required autocomplete="new-password">
      </div>
      <div class="field">
        <label for="current_admin_password_viewer">Current Administrator Password (to authorize change)</label>
        <input type="password" id="current_admin_password_viewer" name="current_admin_password" placeholder="Verify your admin password" required autocomplete="current-password">
      </div>
      <button type="submit" class="btn-primary">Update Viewer Password & Revoke Old Sessions</button>
    </form>

    <div class="danger-zone">
      <div class="danger-info">
        <h3>Sign Out All Viewer Devices</h3>
        <p>Invalidates all existing viewer sessions immediately without changing the shared password.</p>
      </div>
      <form method="POST" action="/api/admin/sign-out-viewers">
        <input type="hidden" name="csrf_token" value="{csrf_clean}">
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          <input type="password" name="current_admin_password" placeholder="Admin password" required style="width:200px" autocomplete="current-password">
          <button type="submit" class="btn-danger" onclick="return confirm('Sign out all active viewer devices right now?')">🚪 Sign Out All Viewers</button>
        </div>
      </form>
    </div>
  </section>

  <!-- Panel 2: Administrator Password -->
  <section class="panel">
    <div class="panel-header">
      <h2>🔐 Change Administrator Password</h2>
      <p>Update your personal administrator login credentials.</p>
    </div>
    <form method="POST" action="/api/admin/change-admin-password" class="form-grid">
      <input type="hidden" name="csrf_token" value="{csrf_clean}">
      <div class="field">
        <label for="current_admin_password">Current Administrator Password</label>
        <input type="password" id="current_admin_password" name="current_admin_password" placeholder="Current admin password" required autocomplete="current-password">
      </div>
      <div class="field">
        <label for="new_admin_password">New Administrator Password</label>
        <input type="password" id="new_admin_password" name="new_admin_password" placeholder="At least 8 characters" required autocomplete="new-password">
      </div>
      <button type="submit" class="btn-primary">Change Admin Password</button>
    </form>
  </section>
</main>
</body>
</html>"""
