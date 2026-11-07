with open('src/styles/home.css', 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = '/* --------------------------------------------------------------------------\n   Featured Hero Section'
end_marker = '/* --------------------------------------------------------------------------\n   Continue Watching Section'

pos1 = content.find(start_marker)
pos2 = content.find(end_marker)
assert pos1 != -1 and pos2 != -1, f"Markers not found: pos1={pos1}, pos2={pos2}"

new_hero_css = '''/* --------------------------------------------------------------------------
   Featured Hero Section — Full-Bleed 100vw Cinematic Spotlight Stage
   -------------------------------------------------------------------------- */
.hero-fullbleed {
  position: relative;
  width: 100vw;
  margin-left: calc(-50vw + 50%);
  margin-right: calc(-50vw + 50%);
  min-height: 540px;
  height: 70vh;
  max-height: 680px;
  overflow: hidden;
  margin-bottom: var(--space-8);
  background: var(--bg);
  display: flex;
  align-items: center;
}

@media (max-width: 1024px) {
  .hero-fullbleed {
    min-height: 480px;
    height: 62vh;
  }
}

@media (max-width: 768px) {
  .hero-fullbleed {
    min-height: 440px;
    height: auto;
    padding-top: var(--space-8);
    padding-bottom: var(--space-6);
  }
}

/* Full-Bleed Backdrop Stage with Slow Ken Burns Continuous Zoom */
.hero-backdrop-stage {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  z-index: 1;
  pointer-events: none;
}

.hero-backdrop-img {
  position: absolute;
  inset: -20px;
  background-size: cover;
  background-position: center 25%;
  background-repeat: no-repeat;
  filter: brightness(0.62) saturate(1.25);
  transition: opacity 0.35s ease-in-out;
}

.hero-backdrop-img.fading {
  opacity: 0.2;
}

/* Very Slow Continuous Ken Burns Zoom */
@keyframes kenBurnsSlowZoom {
  0% {
    transform: scale(1) translate(0, 0);
  }
  100% {
    transform: scale(1.08) translate(-1%, -0.5%);
  }
}

.ken-burns {
  animation: kenBurnsSlowZoom 30s ease-in-out infinite alternate;
}

/* Cinematic Gradient Vignette Overlays: Solid Left for Text, Transparent Right, Fade Bottom */
.hero-gradient-overlay-left {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  background: linear-gradient(
    90deg,
    var(--bg) 0%,
    rgba(9, 10, 15, 0.92) 28%,
    rgba(9, 10, 15, 0.65) 50%,
    rgba(9, 10, 15, 0.2) 75%,
    transparent 100%
  );
}

.hero-gradient-overlay-bottom {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  background: linear-gradient(
    0deg,
    var(--bg) 0%,
    rgba(9, 10, 15, 0.8) 25%,
    transparent 65%
  );
}

.hero-gradient-overlay-top {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 100px;
  z-index: 2;
  pointer-events: none;
  background: linear-gradient(
    180deg,
    rgba(9, 10, 15, 0.75) 0%,
    transparent 100%
  );
}

@media (max-width: 768px) {
  .hero-gradient-overlay-left {
    background: linear-gradient(
      180deg,
      rgba(9, 10, 15, 0.4) 0%,
      rgba(9, 10, 15, 0.88) 60%,
      var(--bg) 100%
    );
  }
}

/* Inner Container with 72px side padding to safely clear navigation arrows */
.hero-inner-container {
  position: relative;
  z-index: 3;
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 72px;
  display: flex;
  align-items: center;
}

@media (max-width: 1024px) {
  .hero-inner-container {
    padding: 0 40px;
  }
}

@media (max-width: 768px) {
  .hero-inner-container {
    padding: 0 20px;
  }
}

.hero-content-wrapper {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-8);
  transition: opacity 0.28s ease, transform 0.28s ease;
}

.hero-content-wrapper.fade-in {
  opacity: 1;
  transform: translateY(0);
}

.hero-content-wrapper.fade-out {
  opacity: 0.15;
  transform: translateY(4px);
}

@media (max-width: 768px) {
  .hero-content-wrapper {
    flex-direction: column-reverse;
    align-items: flex-start;
    gap: var(--space-5);
  }
}

/* Left: Metadata, Display Title & CTAs */
.hero-info-column {
  flex: 1;
  max-width: 640px;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* Badges Row */
.hero-badges-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.hero-badge {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  padding: 4px 10px;
  border-radius: var(--radius-xs);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  line-height: 1;
}

.hero-badge-spotlight {
  background: rgba(255, 123, 57, 0.18);
  border: 1px solid rgba(255, 123, 57, 0.4);
  color: var(--accent);
}

.hero-badge-type {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #e2e8f0;
}

.hero-badge-dub {
  background: rgba(16, 185, 129, 0.15);
  border: 1px solid rgba(16, 185, 129, 0.35);
  color: #34d399;
}

/* Display Title — reduced weight 700, 10% smaller, increased line height */
.hero-display-title {
  margin: var(--space-1) 0;
  font-family: var(--font-display);
  font-size: clamp(1.85rem, 3.4vw, 3.1rem);
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.02em;
  color: #ffffff;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-shadow: 0 4px 16px rgba(0, 0, 0, 0.8);
}

/* Metadata Row with small orange star icon */
.hero-meta-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  font-size: var(--font-size-sm);
  color: var(--dim);
}

.hero-meta-rating {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--accent);
  font-weight: 700;
}

.hero-meta-rating .star-icon {
  color: var(--accent);
  fill: var(--accent);
  flex-shrink: 0;
}

.hero-meta-year,
.hero-meta-quality {
  font-weight: 600;
  color: #cbd5e1;
}

.hero-meta-genres {
  color: #94a3b8;
}

/* Synopsis Text (Clamped to 3 lines) */
.hero-synopsis-text {
  font-size: var(--font-size-base);
  line-height: 1.55;
  color: #cbd5e1;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-width: 580px;
  margin: var(--space-1) 0 var(--space-2) 0;
  text-shadow: 0 2px 6px rgba(0, 0, 0, 0.6);
}

/* Action CTA Buttons */
.hero-action-buttons {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-1);
}

.btn-hero-play {
  background: var(--accent);
  color: #090a0f;
  font-size: 15px;
  font-weight: 700;
  padding: 11px 24px;
  border-radius: var(--radius-sm);
  display: inline-flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  border: none;
  box-shadow: 0 4px 20px var(--accent-glow);
  transition: background var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
}

.btn-hero-play:hover {
  background: var(--accent-hover);
  transform: translateY(-2px) scale(1.02);
  box-shadow: 0 6px 24px var(--accent-glow);
}

.btn-hero-play:active {
  background: var(--accent-active);
  transform: translateY(0) scale(0.98);
}

.btn-hero-watchlist {
  background: rgba(255, 255, 255, 0.08);
  color: #f1f5f9;
  font-size: 14.5px;
  font-weight: 600;
  padding: 11px 20px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(255, 255, 255, 0.18);
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  backdrop-filter: blur(12px);
  transition: all var(--transition-fast);
}

.btn-hero-watchlist:hover {
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(255, 255, 255, 0.35);
  color: #ffffff;
}

.btn-hero-watchlist.active {
  background: rgba(255, 123, 57, 0.15);
  border-color: var(--accent);
  color: var(--accent);
}

/* Slide Pagination Dots — positioned safely under action buttons inside info column */
.hero-pagination-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: var(--space-4);
}

.hero-dot-indicator {
  width: 8px;
  height: 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.3);
  border: none;
  cursor: pointer;
  padding: 0;
  transition: all 0.25s ease;
}

.hero-dot-indicator:hover {
  background: rgba(255, 255, 255, 0.6);
}

.hero-dot-indicator.active {
  width: 28px;
  background: var(--accent);
  box-shadow: 0 0 10px var(--accent-glow);
}

/* Right: Comfortably Padded and Proportionately Scaled Poster Card */
.hero-poster-column {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 32px 32px 0;
  margin-right: 24px;
}

.hero-poster-card {
  position: relative;
  width: 290px;
  height: 435px;
  aspect-ratio: 2 / 3;
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow:
    0 20px 44px -10px rgba(0, 0, 0, 0.95),
    0 0 0 1px rgba(255, 255, 255, 0.12);
  cursor: pointer;
  transform: translateY(0) perspective(1000px) rotateY(-2deg);
  transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.35s ease;
}

.hero-poster-card:hover {
  transform: translateY(-6px) perspective(1000px) rotateY(0deg) scale(1.02);
  box-shadow:
    0 28px 56px -12px rgba(0, 0, 0, 0.95),
    0 0 20px var(--accent-glow),
    0 0 0 1.5px rgba(255, 123, 57, 0.5);
}

.hero-poster-artwork {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.hero-poster-hover-overlay {
  position: absolute;
  inset: 0;
  background: rgba(9, 10, 15, 0.45);
  opacity: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.25s ease;
  backdrop-filter: blur(2px);
}

.hero-poster-card:hover .hero-poster-hover-overlay {
  opacity: 1;
}

.hero-poster-play-badge {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-full);
  background: var(--accent);
  color: #090a0f;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 24px var(--accent-glow);
  transform: scale(0.9);
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

.hero-poster-card:hover .hero-poster-play-badge {
  transform: scale(1.05);
}

@media (max-width: 1024px) {
  .hero-poster-card {
    width: 240px;
    height: 360px;
  }
  .hero-poster-column {
    padding: 20px 16px 20px 0;
    margin-right: 0;
  }
}

@media (max-width: 768px) {
  .hero-poster-column {
    display: none;
  }
}

/* Manual Navigation Arrows — Safe 24px Margins inside Hero, Desktop Hover Only */
.hero-nav-arrows {
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  transform: translateY(-50%);
  display: flex;
  justify-content: space-between;
  padding: 0 24px;
  pointer-events: none;
  z-index: 5;
}

.hero-arrow-btn {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-full);
  background: rgba(14, 16, 24, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.14);
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.25s ease, background var(--transition-fast), transform var(--transition-fast);
  backdrop-filter: blur(8px);
}

.hero-fullbleed:hover .hero-arrow-btn {
  opacity: 1;
  pointer-events: auto;
}

.hero-arrow-btn:hover {
  background: var(--accent);
  border-color: var(--accent);
  color: #090a0f;
  transform: scale(1.08);
}

@media (max-width: 768px) {
  .hero-nav-arrows {
    display: none;
  }
}

/* Reduced Motion Override */
@media (prefers-reduced-motion: reduce) {
  .ken-burns {
    animation: none !important;
  }
  .hero-content-wrapper,
  .hero-poster-card,
  .hero-dot-indicator,
  .hero-arrow-btn,
  .btn-hero-play {
    transition: none !important;
  }
}

'''

updated = content[:pos1] + new_hero_css + content[pos2:]

with open('src/styles/home.css', 'w', encoding='utf-8') as f:
    f.write(updated)

print('home.css hero styles successfully updated!')

