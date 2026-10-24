# Component Specifications: CineStream

Complete UI component specifications for the clean-room rebuild of the streaming catalog.
Every component strictly consumes tokens from `replica/design/tokens.json` (`tokens.css` / Tailwind).

---

### Button
- **variants:** `primary` (accent bg, on-accent text), `secondary` (surface bg, border, text), `ghost` (transparent bg, text, hover surface), `danger` (danger bg, text)
- **sizes:** `sm` (32px height, px-3, text-xs), `md` (40px height, px-4, text-sm), `lg` (48px height, px-6, text-md)
- **states:** `default`, `hover` (brightness-110 / bg-surface-hover), `active` (scale-98), `focus-visible` (2px outline ring var(--color-accent), 2px offset), `disabled` (opacity-50 cursor-not-allowed), `loading` (spinner icon with accessible aria-live status)
- **tokens:** `radius-md`, `font-sans`, `transition-fast`
- **a11y:** Native `<button>`, accessible name via text or `aria-label`, retains label for assistive technologies when loading
- **used on:** All screens (S01–S11)

---

### Input & SearchField
- **variants:** `default` (standard form field), `search` (with search magnifying glass and clear 'X' button)
- **sizes:** `sm` (36px height), `md` (42px height), `lg` (48px height)
- **states:** `default` (surface bg, border-input), `hover` (border-accent/50), `focus` (border-accent, ring-1 ring-accent), `error` (border-danger, text-danger message), `disabled` (surface-hover bg, opacity-50)
- **tokens:** `bg-surface`, `text-text`, `placeholder-text-muted`, `border-border-input`, `radius-md`, `font-sm`
- **a11y:** Associated `<label>` or `aria-label`, `aria-invalid` on validation failure, `aria-describedby` pointing to error hint
- **used on:** S01, S04, S08, S11

---

### HeaderNav
- **variants:** `desktop` (horizontal full bar), `mobile` (compact bar with animated hamburger drawer)
- **states:** `transparent` (top of page over hero), `scrolled` (solid `bg-surface/90` with backdrop-blur-md and bottom border), `menu-open` (mobile drawer slides in from right)
- **tokens:** `h-16 md:h-20`, `bg-surface`, `border-border`, `text-text`, `z-50`
- **a11y:** `<nav role="navigation">`, `<button aria-expanded="bool" aria-controls="mobile-menu">`, focus-trap in mobile drawer
- **used on:** All screens (S01–S11)

---

### SearchBarWithAutocomplete
- **variants:** `header-compact` (collapsible or fixed 280px in nav), `fullscreen-modal` (mobile overlay)
- **states:** `idle`, `typing` (debounced query), `loading` (pulse indicator in input), `results-open` (floating dropdown with up to 6 match rows), `empty-results` ("No titles found" banner)
- **tokens:** `bg-surface`, `border-border`, `shadow-pop`, `radius-lg`, `text-sm`, `z-50`
- **a11y:** `role="combobox"`, `aria-autocomplete="list"`, `aria-expanded="bool"`, keyboard arrow navigation (`ArrowDown`, `ArrowUp`, `Enter`, `Escape`)
- **used on:** S01, S02, S03, S04

---

### MediaPosterCard
- **variants:** `movie` (2:3 aspect ratio poster), `tv-show` (2:3 poster with episode/season badge pill), `compact-row` (horizontal 16:9 thumbnail for history/watchlist)
- **sizes:** standard (180px–220px width in responsive grid)
- **states:** `default`, `hover` (scale-105, poster shadow-glow, gradient overlay fades in revealing play button and bookmark heart), `focus-visible` (accent border ring), `image-loading` (shimmer skeleton placeholder)
- **tokens:** `radius-md`, `bg-surface`, `shadow-card`, `transition-base`
- **a11y:** Clickable `<a href="...">` enclosing title, `aria-label` with title, year, and rating; bookmark icon button has dedicated `aria-label="Add to Watchlist"`
- **used on:** S01, S02, S03, S04, S09

---

### HeroSlider
- **variants:** `full-bleed` (panoramic 21:9 hero with gradient masks to bg)
- **states:** `slide-active`, `transitioning` (smooth fade-in slide), `paused-on-hover`
- **tokens:** `h-[460px] md:h-[600px]`, `text-display`, `text-text`, `bg-gradient-to-t from-bg via-bg/40 to-transparent`
- **a11y:** `aria-roledescription="carousel"`, carousel previous/next buttons with `aria-label`, slide indicators with `aria-current="step"`, pauses rotation when user hovers or tabs into carousel
- **used on:** S01

---

### VideoPlayerBox
- **variants:** `standard` (16:9 responsive embed), `theater-mode` (full viewport width with dimmed surround), `fullscreen`
- **states:** `poster-pre-roll` (shows backdrop with prominent play CTA), `buffering` (spinner over darkened backdrop), `playing`, `error-fallback` (actionable card: "Stream connection timed out. Switch to Server 2 or report link")
- **tokens:** `aspect-video`, `bg-black`, `border-border`, `radius-lg`, `shadow-pop`
- **a11y:** Keyboard spacebar play/pause, M key mute, F key fullscreen; iframe uses `sandbox="allow-scripts allow-same-origin allow-presentation"` and explicit `title="Streaming Player"`
- **used on:** S05, S07

---

### ServerSwitcher
- **variants:** `pill-tabs` (horizontal scrollable pills), `dropdown-select` (compact mobile fallback)
- **states:** `active` (accent bg, on-accent text, glowing pulse indicator), `inactive` (surface bg, border, text-muted), `hover` (surface-hover bg, text), `testing-health` (small ping dot)
- **tokens:** `radius-pill`, `font-xs`, `transition-fast`
- **a11y:** `role="tablist"`, each server button has `role="tab"`, `aria-selected="bool"`, left/right arrow key navigation
- **used on:** S05, S07

---

### QualityBadge & AudioLanguageBadge
- **variants:** `quality` (4K Ultra in cyan, 1080p in slate-blue, 720p in neutral, CAM in warning-amber), `audio` (Hindi Dubbed in emerald, Dual Audio in purple, Original in slate)
- **states:** `default`
- **tokens:** `font-xs font-semibold`, `px-2 py-0.5`, `radius-xs`, `border`
- **a11y:** High-contrast text, clear semantic text value (not icon-only)
- **used on:** S01, S02, S03, S05, S07

---

### EpisodeSelectorGrid
- **variants:** `season-tabs` (tabs for Season 1, Season 2), `episode-cards` (grid of episode cards with thumbnail, episode number, title, and air date)
- **states:** `current-episode` (accent border, glowing badge "Now Playing"), `watched` (subtle checkmark icon), `unwatched`
- **tokens:** `bg-surface`, `border-border`, `radius-md`, `font-sm`
- **a11y:** `role="region" aria-label="Episodes list"`, accessible links with episode number and full title
- **used on:** S06, S07

---

### FilterPillGroup
- **variants:** `single-select` (sort order: Latest, Popular, Rating), `multi-facet-dropdown` (Genre, Year, Quality, Language)
- **states:** `default`, `active-filter` (accent border and checkmark), `open-dropdown`, `cleared`
- **tokens:** `bg-surface`, `border-border`, `radius-pill`, `font-sm`
- **a11y:** `aria-haspopup="listbox"`, `aria-expanded="bool"`, escape key closes dropdown menu
- **used on:** S02, S03, S04

---

### DownloadLinksTable
- **variants:** `accordion` (expandable table sorted by quality e.g. 1080p, 720p, 480p)
- **states:** `collapsed`, `expanded`, `download-clicked`
- **tokens:** `bg-surface`, `border-border`, `radius-md`, `text-sm`
- **a11y:** Clean table semantics `<table>`, `<th>`, `<td>` with clear column headers (Quality, Resolution, File Size, Host, Download Action)
- **used on:** S05

---

### ModalDialog
- **variants:** `center-dialog` (broken link report, trailer popup), `sheet` (mobile bottom sheet)
- **states:** `hidden`, `entering` (fade in backdrop + scale up 0.95 -> 1.0), `visible`, `exiting`
- **tokens:** `bg-surface`, `border-border`, `shadow-pop`, `radius-xl`, `z-50`
- **a11y:** `role="dialog"`, `aria-modal="true"`, `aria-labelledby="dialog-title"`, focus trapped inside modal, escape key dismisses, focus returned to trigger on close
- **used on:** S06 (Trailer), S08 (Report broken link)

---

### ToastNotification
- **variants:** `success` (green indicator), `error` (danger indicator), `info` (cyan accent indicator)
- **states:** `entering` (slide in from top-right), `visible` (auto-dismiss after 4000ms), `exiting`
- **tokens:** `bg-surface`, `border-border`, `shadow-card`, `radius-md`, `font-sm`
- **a11y:** `role="status"`, `aria-live="polite"` (or `assertive` for critical errors)
- **used on:** All screens (S01–S11)

---

### EmptyState
- **variants:** `no-search-results`, `empty-watchlist`, `network-error-404`
- **states:** `default`
- **tokens:** `py-16 text-center`, `text-text-muted`, `radius-lg`
- **a11y:** Semantic icon with `aria-hidden="true"`, heading `<h3>`, actionable CTA button ("Clear all filters", "Browse Trending")
- **used on:** S02, S04, S09
