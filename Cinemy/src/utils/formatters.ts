/**
 * Generates an SVG data URL fallback placeholder for cards lacking posters.
 * Replicates the verified Vanilla getPosterFallbackSvg implementation.
 */
export function getPosterFallbackSvg(title: string, year?: string | null): string {
  const safeTitle = (title || 'CineMyMovies')
    .replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
    .slice(0, 36);
  const safeYear = year ? String(year).slice(0, 4) : '';

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="450" viewBox="0 0 300 450">
    <defs>
      <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#181a20" />
        <stop offset="100%" stop-color="#0e0f13" />
      </linearGradient>
    </defs>
    <rect width="300" height="450" fill="url(#bg)"/>
    <rect x="1" y="1" width="298" height="448" fill="none" stroke="#262932" stroke-width="2"/>
    <g transform="translate(150, 180)" fill="#ff7b39" opacity="0.8">
      <path d="M-24 -24 h48 v48 h-48 z" fill="none"/>
      <path d="M-18 -12 h36 v24 h-36 z" fill="#ff7b39" opacity="0.3"/>
      <polygon points="-6,-6 -6,6 8,0" fill="#ff7b39"/>
    </g>
    <text x="150" y="270" font-family="system-ui, sans-serif" font-size="16" font-weight="700" fill="#ececed" text-anchor="middle">
      ${safeTitle}
    </text>
    ${
      safeYear
        ? `<text x="150" y="300" font-family="system-ui, sans-serif" font-size="13" font-weight="500" fill="#9aa0aa" text-anchor="middle">${safeYear}</text>`
        : ''
    }
  </svg>`;

  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

/**
 * Normalizes poster URLs and substitutes fallback placeholder for null/invalid URLs.
 */
export function getPosterUrl(poster: string | null | undefined, title: string, year?: string | null): string {
  const val = (poster || '').trim();
  if (!val || val === 'None' || val === 'null' || val.includes('logo.png') || val.startsWith('/assets/')) {
    return getPosterFallbackSvg(title, year);
  }
  return val;
}

/**
 * Formats IMDb / numerical rating cleanly
 */
export function formatRating(rating: number | string | null | undefined, imdb: string | null | undefined): string | null {
  if (imdb && imdb.trim()) {
    const clean = imdb.replace(/^(IMDb:\s*|★\s*)/i, '').trim();
    if (clean) return clean;
  }
  if (rating !== null && rating !== undefined) {
    const num = typeof rating === 'number' ? rating : parseFloat(rating);
    if (!isNaN(num) && num > 0) {
      return num.toFixed(1);
    }
  }
  return null;
}

/**
 * Formats duration in seconds into human-readable string (e.g. 1h 45m or 42m)
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || !Number.isFinite(seconds) || seconds <= 0) return '';
  const totalMinutes = Math.round(seconds / 60);
  if (totalMinutes < 60) return `${totalMinutes}m`;
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}


