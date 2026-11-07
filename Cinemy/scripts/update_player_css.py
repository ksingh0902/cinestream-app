import os

path = 'src/features/player/styles/player.css'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()

# Replace spinner top color
t = t.replace('border-top-color: #e50914;', 'border-top-color: var(--accent);')

# Replace primary button background
t = t.replace('background: #e50914;', 'background: var(--accent); color: #090a0f;')

# Replace timeline progress
t = t.replace('background: #e50914;', 'background: var(--accent);')

# Replace volume slider accent
t = t.replace('accent-color: #e50914;', 'accent-color: var(--accent);')

# Replace subtitles active button
t = t.replace('.player-subtitles-btn.active {\n  background: #e50914;\n  border-color: #f40612;\n  color: #fff;\n}', '.player-subtitles-btn.active {\n  background: var(--accent);\n  border-color: var(--accent);\n  color: #090a0f;\n}')

# Replace episode button styling in header
old_ep_btn = '''.player-btn-episodes {
  background: rgba(124, 58, 237, 0.2);
  border: 1px solid rgba(124, 58, 237, 0.4);
  color: #e9d5ff;
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
  white-space: nowrap;
}

.player-btn-episodes:hover {
  background: rgba(124, 58, 237, 0.4);
  border-color: #a855f7;
  color: #fff;
}'''

new_ep_btn = '''.player-btn-episodes {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.18);
  color: #f1f5f9;
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
  white-space: nowrap;
}

.player-btn-episodes:hover {
  background: rgba(255, 123, 57, 0.18);
  border-color: var(--accent);
  color: var(--accent);
}'''

t = t.replace(old_ep_btn, new_ep_btn)

# Replace server bar wrap and server pills
old_server_block = '''.player-server-bar-wrap {
  position: absolute;
  bottom: 84px;
  left: 24px;
  right: 24px;
  z-index: 19;
  display: flex;
  justify-content: center;
  pointer-events: auto;
  transition: opacity 0.3s ease, transform 0.3s ease;
  transform: translateY(0);
}

.player-server-bar-wrap.hidden {
  opacity: 0;
  transform: translateY(10px);
  pointer-events: none;
}

.player-server-switcher {
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(12, 16, 28, 0.88);
  border: 1px solid #1e293b;
  padding: 6px 14px;
  border-radius: 24px;
  backdrop-filter: blur(8px);
  max-width: 90vw;
  overflow-x: auto;
}

.server-switcher-label {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 600;
  white-space: nowrap;
}

.server-pill-list {
  display: flex;
  align-items: center;
  gap: 8px;
}

.server-pill-btn {
  background: #1e293b;
  color: #f8fafc;
  border: 1px solid #334155;
  border-radius: 16px;
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  transition: all 0.2s;
}

.server-pill-btn:hover {
  background: #3b82f6;
  border-color: #60a5fa;
  color: #fff;
}

.server-pill-btn.active {
  background: #2563eb;
  border-color: #60a5fa;
  color: #fff;
  font-weight: 700;
  box-shadow: 0 0 10px rgba(37, 99, 235, 0.5);
}

.server-pill-btn.hls-tag.active {
  background: #16a34a;
  border-color: #4ade80;
  box-shadow: 0 0 10px rgba(22, 163, 74, 0.5);
}'''

new_server_block = '''.player-server-bar-wrap {
  position: absolute;
  bottom: 84px;
  left: 24px;
  right: 24px;
  z-index: 19;
  display: flex;
  justify-content: center;
  pointer-events: auto;
  transition: opacity 0.3s ease, transform 0.3s ease;
  transform: translateY(0);
}

.player-server-bar-wrap.iframe-mode {
  bottom: 24px;
}

.player-server-bar-wrap.hls-mode {
  bottom: 84px;
}

.player-server-bar-wrap.hidden {
  opacity: 0;
  transform: translateY(10px);
  pointer-events: none;
}

.player-server-switcher {
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(9, 10, 15, 0.88);
  border: 1px solid rgba(255, 255, 255, 0.12);
  padding: 6px 14px;
  border-radius: 24px;
  backdrop-filter: blur(12px);
  max-width: 90vw;
  overflow-x: auto;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
}

.server-switcher-label {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 600;
  white-space: nowrap;
}

.server-pill-list {
  display: flex;
  align-items: center;
  gap: 8px;
}

.server-pill-btn {
  background: rgba(255, 255, 255, 0.08);
  color: #f8fafc;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 16px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  transition: all 0.2s ease;
}

.server-pill-btn:hover {
  background: rgba(255, 123, 57, 0.2);
  border-color: var(--accent);
  color: #fff;
}

.server-pill-btn.active,
.server-pill-btn.hls-tag.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #090a0f;
  font-weight: 700;
  box-shadow: 0 0 14px var(--accent-glow);
}'''

t = t.replace(old_server_block, new_server_block)

# Replace remaining blues in episode drawer / toast
t = t.replace('border-color: #3b82f6;', 'border-color: var(--accent);')
t = t.replace('box-shadow: inset 3px 0 0 #3b82f6;', 'box-shadow: inset 3px 0 0 var(--accent);')
t = t.replace('background: #3b82f6;', 'background: var(--accent); color: #090a0f;')
t = t.replace('color: #3b82f6;', 'color: var(--accent);')
t = t.replace('color: #e50914;', 'color: var(--accent);')

with open(path, 'w', encoding='utf-8') as f:
    f.write(t)

print('player.css successfully updated to CINEMY design tokens!')

