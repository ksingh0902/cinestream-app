import os

with open('src/features/player/components/PlayerModal.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

import_target = "import React, { useState, useEffect, useRef, useCallback } from 'react';"
import_replacement = "import React, { useState, useEffect, useRef, useCallback } from 'react';\nimport { ArrowLeft, Tv, X, Languages } from 'lucide-react';"

if import_target in text:
    text = text.replace(import_target, import_replacement, 1)

old_header = """        <div className="player-header-left">
          <button
            className="player-btn-back"
            onClick={handleClose}
            title="Back to Home (Escape)"
            aria-label="Back to Home"
          >
            ← Back to Home
          </button>
          <div className="player-meta-badges">
            {currentTarget.source && (
              <span className="player-badge source-badge">
                {currentTarget.source === 'ask4movie'
                  ? '🍿 ask'
                  : currentTarget.source === 'dooflix'
                    ? '▶️ doo'
                    : currentTarget.source === 'movies7'
                      ? '⚡ 7'
                      : '🎬 ym'}
              </span>
            )}
            {currentTarget.isHindiDubbed && (
              <span className="player-badge dubbed-badge">🎙️ Hindi Dubbed</span>
            )}
            {isSeries && (
              <span className="player-badge series-badge">
                S{String(activeSeasonNum).padStart(2, '0')}·E{String(activeEpisodeNum).padStart(2, '0')}
              </span>
            )}
          </div>
          <h2 className="player-title" title={`${baseTitle}${epSuffix}${yr}`}>
            {baseTitle}
            {epSuffix}
            {yr}
          </h2>
        </div>

        <div className="player-header-right">
          {/* Episode Drawer Button for Series */}
          {isSeries && (
            <button
              className="player-btn-episodes"
              onClick={() => setIsDrawerOpen(true)}
              title="Browse Episodes & Seasons (e)"
              aria-label="Episodes & Seasons"
            >
              📺 Episodes & Seasons
            </button>
          )}

          <button
            className="player-btn-close"
            onClick={handleClose}
            title="Close Player (Escape)"
            aria-label="Close Player"
          >
            ✕ Close
          </button>
        </div>"""

new_header = """        <div className="player-header-left">
          <button
            className="player-btn-back"
            onClick={handleClose}
            title="Back to Home (Escape)"
            aria-label="Back to Home"
          >
            <ArrowLeft size={16} strokeWidth={1.5} />
            <span>Back to Home</span>
          </button>
          <div className="player-meta-badges">
            {currentTarget.source && (
              <span className={`player-badge source-badge ${currentTarget.source}`}>
                {currentTarget.source === 'ask4movie'
                  ? 'ASK'
                  : currentTarget.source === 'dooflix'
                    ? 'DOO'
                    : currentTarget.source === 'movies7'
                      ? 'M7'
                      : 'YM'}
              </span>
            )}
            {currentTarget.isHindiDubbed && (
              <span className="player-badge dubbed-badge">
                <Languages size={12} strokeWidth={1.5} />
                <span>Hindi Dubbed</span>
              </span>
            )}
            {isSeries && (
              <span className="player-badge series-badge">
                S{String(activeSeasonNum).padStart(2, '0')}·E{String(activeEpisodeNum).padStart(2, '0')}
              </span>
            )}
          </div>
          <h2 className="player-title" title={`${baseTitle}${epSuffix}${yr}`}>
            {baseTitle}
            {epSuffix}
            {yr}
          </h2>
        </div>

        <div className="player-header-right">
          {/* Episode Drawer Button for Series */}
          {isSeries && (
            <button
              className="player-btn-episodes"
              onClick={() => setIsDrawerOpen(true)}
              title="Browse Episodes & Seasons (e)"
              aria-label="Episodes & Seasons"
            >
              <Tv size={15} strokeWidth={1.5} />
              <span>Episodes & Seasons</span>
            </button>
          )}

          <button
            className="player-btn-close"
            onClick={handleClose}
            title="Close Player (Escape)"
            aria-label="Close Player"
          >
            <X size={16} strokeWidth={1.5} />
            <span>Close</span>
          </button>
        </div>"""

if old_header in text:
    text = text.replace(old_header, new_header, 1)

old_bar_wrap = 'className={`player-server-bar-wrap ${isControlsVisible ? \'visible\' : \'hidden\'}`}'
new_bar_wrap = 'className={`player-server-bar-wrap ${isIframe ? \'iframe-mode\' : \'hls-mode\'} ${isControlsVisible ? \'visible\' : \'hidden\'}`}'

if old_bar_wrap in text:
    text = text.replace(old_bar_wrap, new_bar_wrap, 1)

with open('src/features/player/components/PlayerModal.tsx', 'w', encoding='utf-8') as f:
    f.write(text)

print('PlayerModal.tsx successfully updated!')

