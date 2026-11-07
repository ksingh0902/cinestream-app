import os

# 1. EpisodeDrawer.tsx
path = 'src/features/player/components/EpisodeDrawer.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
if "import { X } from 'lucide-react';" not in t:
    t = t.replace("import React, { useState, useEffect, useRef } from 'react';", "import React, { useState, useEffect, useRef } from 'react';\nimport { X } from 'lucide-react';", 1)
t = t.replace('<button\n            className="drawer-close-btn"\n            onClick={onClose}\n            title="Close drawer"\n            aria-label="Close episode drawer"\n          >\n            ✕\n          </button>', '<button\n            className="drawer-close-btn"\n            onClick={onClose}\n            title="Close drawer"\n            aria-label="Close episode drawer"\n          >\n            <X size={18} strokeWidth={1.5} />\n          </button>')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('1. EpisodeDrawer.tsx updated')

# 2. EpisodeNavigation.tsx
path = 'src/features/player/components/EpisodeNavigation.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("import React from 'react';", "import React from 'react';\nimport { SkipBack, SkipForward } from 'lucide-react';")
t = t.replace('⏮ <span className="ep-nav-text">Prev Ep</span>', '<SkipBack size={14} strokeWidth={1.5} /> <span className="ep-nav-text">Prev Ep</span>')
t = t.replace('<span className="ep-nav-text">Next Ep</span> ⏭', '<span className="ep-nav-text">Next Ep</span> <SkipForward size={14} strokeWidth={1.5} />')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('2. EpisodeNavigation.tsx updated')

# 3. NextEpisodeToast.tsx
path = 'src/features/player/components/NextEpisodeToast.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("import React, { useEffect, useState, useRef } from 'react';", "import React, { useEffect, useState, useRef } from 'react';\nimport { Play, X } from 'lucide-react';")
t = t.replace('▶ Play Now', '<Play size={14} strokeWidth={1.5} fill="currentColor" /> <span>Play Now</span>')
t = t.replace('<button\n          className="btn-next-ep-cancel"\n          onClick={onCancel}\n          title={isCountdown ? \'Cancel Auto-Play Countdown\' : \'Dismiss Preview\'}\n        >\n          ✕\n        </button>', '<button\n          className="btn-next-ep-cancel"\n          onClick={onCancel}\n          title={isCountdown ? \'Cancel Auto-Play Countdown\' : \'Dismiss Preview\'}\n        >\n          <X size={16} strokeWidth={1.5} />\n        </button>')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('3. NextEpisodeToast.tsx updated')

# 4. ContinueWatchingCard.tsx
path = 'src/features/continue-watching/components/ContinueWatchingCard.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("import React, { useState } from 'react';", "import React, { useState } from 'react';\nimport { Play, X, Languages } from 'lucide-react';")
t = t.replace('return <span className="cw-card-badge ask">🍿 ask</span>;', 'return <span className="cw-card-badge ask">ASK</span>;')
t = t.replace('return <span className="cw-card-badge doo">📺 doo</span>;', 'return <span className="cw-card-badge doo">DOO</span>;')
t = t.replace('return <span className="cw-card-badge m7">🎬 m7</span>;', 'return <span className="cw-card-badge m7">M7</span>;')
t = t.replace('return <span className="cw-card-badge ym">🎬 ym</span>;', 'return <span className="cw-card-badge ym">YM</span>;')
t = t.replace('<div className="cw-play-icon">▶</div>', '<div className="cw-play-icon"><Play size={20} strokeWidth={1.5} fill="currentColor" /></div>')
t = t.replace('>\n        ×\n      </button>', '>\n        <X size={14} strokeWidth={1.5} />\n      </button>')
t = t.replace('{item.isHindiDubbed && <span className="cw-card-badge dub">🎙️ Dub</span>}', '{item.isHindiDubbed && <span className="cw-card-badge dub"><Languages size={10} strokeWidth={1.5} /><span>DUB</span></span>}')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('4. ContinueWatchingCard.tsx updated')

# 5. MovieDetailPage.tsx
path = 'src/features/movie-details/MovieDetailPage.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("import React, { useState, useEffect } from 'react';", "import React, { useState, useEffect } from 'react';\nimport { ArrowLeft, Star, Clock, Play, Check, Bookmark, AlertTriangle } from 'lucide-react';")
t = t.replace('← Back', '<ArrowLeft size={16} strokeWidth={1.5} /> <span>Back</span>')
t = t.replace('{ratingBadge && <span className="badge-tag rating">★ {ratingBadge}</span>}', '{ratingBadge && <span className="badge-tag rating"><Star size={12} strokeWidth={1.5} fill="currentColor" /> {ratingBadge}</span>}')
t = t.replace('{formattedRuntime && <span className="meta-item">⏱ {formattedRuntime}</span>}', '{formattedRuntime && <span className="meta-item"><Clock size={13} strokeWidth={1.5} /> {formattedRuntime}</span>}')
t = t.replace('<span className="play-icon">▶</span>', '<Play size={16} strokeWidth={1.5} fill="currentColor" style={{ verticalAlign: "middle", marginRight: 6 }} />')
t = t.replace("{isSaved ? '✓ In My List' : '+ Add to My List'}", "{isSaved ? (<><Check size={16} strokeWidth={1.5} /> <span>In My List</span></>) : (<><Bookmark size={16} strokeWidth={1.5} /> <span>Add to List</span></>)}")
t = t.replace('<div className="error-icon">⚠️</div>', '<div className="error-icon"><AlertTriangle size={36} strokeWidth={1.5} /></div>')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('5. MovieDetailPage.tsx updated')

# 6. SeriesDetailPage.tsx
path = 'src/features/series-details/SeriesDetailPage.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("import React, { useState, useEffect, useRef } from 'react';", "import React, { useState, useEffect, useRef } from 'react';\nimport { ArrowLeft, Star, Play, Check, Bookmark, Tv, AlertTriangle } from 'lucide-react';")
t = t.replace('← Back', '<ArrowLeft size={16} strokeWidth={1.5} /> <span>Back</span>')
t = t.replace('{ratingBadge && <span className="badge-tag rating">★ {ratingBadge}</span>}', '{ratingBadge && <span className="badge-tag rating"><Star size={12} strokeWidth={1.5} fill="currentColor" /> {ratingBadge}</span>}')
t = t.replace('<span className="play-icon">▶</span>', '<Play size={16} strokeWidth={1.5} fill="currentColor" style={{ verticalAlign: "middle", marginRight: 6 }} />')
t = t.replace("{isSaved ? '✓ In My List' : '+ Add to My List'}", "{isSaved ? (<><Check size={16} strokeWidth={1.5} /> <span>In My List</span></>) : (<><Bookmark size={16} strokeWidth={1.5} /> <span>Add to List</span></>)}")
t = t.replace('☰ Episodes ({totalEpisodesCount})', '<Tv size={16} strokeWidth={1.5} /> <span>Episodes ({totalEpisodesCount})</span>')
t = t.replace('<div className="error-icon">⚠️</div>', '<div className="error-icon"><AlertTriangle size={36} strokeWidth={1.5} /></div>')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('6. SeriesDetailPage.tsx updated')

# 7. AdminConsolePage.tsx
path = 'src/features/admin/AdminConsolePage.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("import React, { useState, useEffect } from 'react';", "import React, { useState, useEffect } from 'react';\nimport { ShieldAlert, Settings, RefreshCw, Check, AlertTriangle, Activity, BarChart3, Sparkles, KeyRound, ArrowLeft } from 'lucide-react';")
t = t.replace('<div className="forbidden-icon">🚫</div>', '<div className="forbidden-icon"><ShieldAlert size={48} strokeWidth={1.5} /></div>')
t = t.replace('← Return to Home', '<ArrowLeft size={16} strokeWidth={1.5} /> <span>Return to Home</span>')
t = t.replace('<h1 className="page-title">⚙️ Administrator Control Console</h1>', '<h1 className="page-title" style={{ display: "flex", alignItems: "center", gap: 8 }}><Settings size={24} strokeWidth={1.5} /> Administrator Control Console</h1>')
t = t.replace('🔄 Refresh Metrics', '<RefreshCw size={14} strokeWidth={1.5} /> <span>Refresh Metrics</span>')
t = t.replace("{actionNotice.type === 'success' ? '✅' : '⚠️'} {actionNotice.text}", "{actionNotice.type === 'success' ? <Check size={14} strokeWidth={1.5} /> : <AlertTriangle size={14} strokeWidth={1.5} />} <span>{actionNotice.text}</span>")
t = t.replace('<h3 className="card-header">🏥 System Health & Database</h3>', '<h3 className="card-header" style={{ display: "flex", alignItems: "center", gap: 6 }}><Activity size={16} strokeWidth={1.5} /> System Health & Database</h3>')
t = t.replace('<h3 className="card-header">📊 Catalogue Coverage</h3>', '<h3 className="card-header" style={{ display: "flex", alignItems: "center", gap: 6 }}><BarChart3 size={16} strokeWidth={1.5} /> Catalogue Coverage</h3>')
t = t.replace('<h3 className="card-header">🔄 Scraper & Catalogue Sync</h3>', '<h3 className="card-header" style={{ display: "flex", alignItems: "center", gap: 6 }}><RefreshCw size={16} strokeWidth={1.5} /> Scraper & Catalogue Sync</h3>')
t = t.replace("{isTriggeringSync ? 'Starting Sync...' : '🚀 Trigger Catalogue Sync'}", "{isTriggeringSync ? 'Starting Sync...' : (<><Sparkles size={14} strokeWidth={1.5} /> <span>Trigger Catalogue Sync</span></>)}")
t = t.replace('<h3 className="card-header">🔐 Viewer Account Governance</h3>', '<h3 className="card-header" style={{ display: "flex", alignItems: "center", gap: 6 }}><KeyRound size={16} strokeWidth={1.5} /> Viewer Account Governance</h3>')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('7. AdminConsolePage.tsx updated')

# 8. ProfilePage.tsx
path = 'src/features/profile/ProfilePage.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("import React from 'react';", "import React from 'react';\nimport { UserRound, Shield, Bookmark, Lock, House, Settings, Info, LogOut } from 'lucide-react';")
t = t.replace('<div className="profile-avatar-placeholder">👤</div>', '<div className="profile-avatar-placeholder"><UserRound size={48} strokeWidth={1.5} /></div>')
t = t.replace('<span className="detail-icon">👤</span>', '<span className="detail-icon"><UserRound size={18} strokeWidth={1.5} /></span>')
t = t.replace('<span className="detail-icon">🛡️</span>', '<span className="detail-icon"><Shield size={18} strokeWidth={1.5} /></span>')
t = t.replace('<span className="detail-icon">📑</span>', '<span className="detail-icon"><Bookmark size={18} strokeWidth={1.5} /></span>')
t = t.replace('<span className="detail-icon">🔒</span>', '<span className="detail-icon"><Lock size={18} strokeWidth={1.5} /></span>')
t = t.replace('🎬 My List ({watchlistCount})', '<Bookmark size={15} strokeWidth={1.5} /> <span>My List ({watchlistCount})</span>')
t = t.replace('🏠 Home & Continue Watching', '<House size={15} strokeWidth={1.5} /> <span>Home & Continue Watching</span>')
t = t.replace('⚙️ Open Admin Console', '<Settings size={15} strokeWidth={1.5} /> <span>Open Admin Console</span>')
t = t.replace('<span className="policy-icon">ℹ️</span>', '<span className="policy-icon"><Info size={16} strokeWidth={1.5} /></span>')
t = t.replace('🚪 Sign Out of CineMyMovies', '<LogOut size={16} strokeWidth={1.5} /> <span>Sign Out of CineMyMovies</span>')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('8. ProfilePage.tsx updated')

# 9. MyListPage.tsx
path = 'src/features/watchlist/MyListPage.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("import React, { useState, useMemo } from 'react';", "import React, { useState, useMemo } from 'react';\nimport { HardDrive, Bookmark, X } from 'lucide-react';")
t = t.replace('<span className="disclosure-icon">💾</span>', '<span className="disclosure-icon"><HardDrive size={15} strokeWidth={1.5} /></span>')
t = t.replace('<div className="empty-icon">🎬</div>', '<div className="empty-icon"><Bookmark size={40} strokeWidth={1.5} /></div>')
t = t.replace('>\n                    ✕\n                  </button>', '>\n                    <X size={14} strokeWidth={1.5} />\n                  </button>')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('9. MyListPage.tsx updated')

# 10. GenrePage.tsx
path = 'src/features/catalogue/GenrePage.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("import React, { useState, useEffect } from 'react';", "import React, { useState, useEffect } from 'react';\nimport { AlertTriangle } from 'lucide-react';")
t = t.replace('<p className="error-text">⚠️ {error}</p>', '<p className="error-text"><AlertTriangle size={16} strokeWidth={1.5} style={{ verticalAlign: "middle", marginRight: 6 }} /> {error}</p>')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('10. GenrePage.tsx updated')

# 11. SearchPage.tsx
path = 'src/features/search/SearchPage.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("import React, { useState, useEffect, useRef } from 'react';", "import React, { useState, useEffect, useRef } from 'react';\nimport { Search, X, AlertTriangle } from 'lucide-react';")
t = t.replace('<span className="search-icon-large">🔍</span>', '<Search size={20} strokeWidth={1.5} />')
t = t.replace('>\n            ✕\n          </button>', '>\n            <X size={16} strokeWidth={1.5} />\n          </button>')
t = t.replace('<p className="error-text">⚠️ {error}</p>', '<p className="error-text"><AlertTriangle size={16} strokeWidth={1.5} style={{ verticalAlign: "middle", marginRight: 6 }} /> {error}</p>')
t = t.replace('<div className="empty-icon">🔍</div>', '<div className="empty-icon"><Search size={40} strokeWidth={1.5} /></div>')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('11. SearchPage.tsx updated')

# 12. ErrorBanner.tsx
path = 'src/components/common/ErrorBanner.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("import React from 'react';", "import React from 'react';\nimport { Radio, AlertTriangle, RefreshCw } from 'lucide-react';")
t = t.replace("<span className=\"error-icon\">{isOutage ? '📡' : '⚠️'}</span>", "<span className=\"error-icon\">{isOutage ? <Radio size={16} strokeWidth={1.5} /> : <AlertTriangle size={16} strokeWidth={1.5} />}</span>")
t = t.replace('🔄 Retry', '<RefreshCw size={13} strokeWidth={1.5} /> <span>Retry</span>')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('12. ErrorBanner.tsx updated')

# 13. ContentGrid.tsx
path = 'src/components/home/ContentGrid.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("import React from 'react';", "import React from 'react';\nimport { Sparkles } from 'lucide-react';")
t = t.replace('<span>✨ You have viewed all available titles in this collection.</span>', '<span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Sparkles size={14} strokeWidth={1.5} /> You have viewed all available titles in this collection.</span>')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('13. ContentGrid.tsx updated')

# 14. ActionNoticeModal.tsx
path = 'src/components/home/ActionNoticeModal.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("import React from 'react';", "import React from 'react';\nimport { X } from 'lucide-react';")
t = t.replace('>\n            ✕\n          </button>', '>\n            <X size={16} strokeWidth={1.5} />\n          </button>')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('14. ActionNoticeModal.tsx updated')

# 15. App.tsx
path = 'src/App.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
if "import { Lock } from 'lucide-react';" not in t:
    t = t.replace("import React from 'react';", "import React from 'react';\nimport { Lock } from 'lucide-react';", 1)
t = t.replace('🔒 You are browsing in guest mode.', '<Lock size={13} strokeWidth={1.5} style={{ verticalAlign: "middle", marginRight: 6 }} /> You are browsing in guest mode.')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('15. App.tsx updated')

print('All 15 files successfully updated with Lucide icon system!')

