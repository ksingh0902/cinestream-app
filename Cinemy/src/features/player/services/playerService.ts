import {
  StreamInfo,
  StreamServer,
  PlaybackTarget,
  SeriesSeasonResponse,
  NextEpisodeInfo,
  PreviousEpisodeInfo,
} from '../types';

export const PERMITTED_IFRAME_HOSTS = [
  'embed.vidsrc.si',
  'vidsrc.si',
  'vidsrc.pm',
  'vidfast.pro',
  'embed.filmu.in',
  'vidly.pro',
  'play2.123embed.net',
  'player.videasy.to',
  'vidcore.org',
  'www.2embed.cc',
  '2embed.cc',
  'vidup.to',
  'cinesrc.st',
  '111movies.net',
  'vidlink.pro',
  'primesrc.me',
];

/**
 * Validates if an iframe URL's hostname belongs to the approved upstream hosts.
 */
export function isPermittedIframeOrigin(url: string): boolean {
  try {
    const parsed = new URL(url, window.location.origin);
    const host = parsed.hostname.toLowerCase();
    return PERMITTED_IFRAME_HOSTS.some((h) => host === h || host.endsWith('.' + h));
  } catch {
    return false;
  }
}

/**
 * Checks whether an upstream provider supports genuine postMessage telemetry.
 * Providers without telemetry (e.g. FilmU / Vidly) do not emit postMessage signals to parent.
 */
export function providerSupportsTelemetry(server?: StreamServer | null): boolean {
  if (!server) return false;
  const url = (server.url || '').toLowerCase();
  const label = (server.label || '').toLowerCase();
  // FilmU / Vidly does not expose postMessage telemetry
  if (url.includes('filmu') || label.includes('filmu') || url.includes('vidly.pro')) {
    return false;
  }
  return true;
}

/**
 * Resolves stream information from the existing FastAPI stream endpoint.
 */
export async function resolveStream(
  movieId: number | string,
  options: {
    fresh?: boolean;
    season?: number | null;
    episode?: number | null;
    signal?: AbortSignal;
  } = {}
): Promise<StreamInfo> {
  const params = new URLSearchParams();
  if (options.fresh) params.set('fresh', '1');
  if (options.season != null && options.episode != null) {
    params.set('season', String(options.season));
    params.set('episode', String(options.episode));
  }

  const qs = params.toString();
  const url = `/api/stream/${movieId}${qs ? `?${qs}` : ''}`;

  const res = await fetch(url, {
    method: 'GET',
    credentials: 'include',
    signal: options.signal,
  });

  if (!res.ok) {
    let errorDetail = `Stream resolution failed with status ${res.status}`;
    try {
      const errJson = await res.json();
      if (errJson && errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // Non-JSON error body
    }
    throw new Error(errorDetail);
  }

  const data = await res.json();
  const playUrl = data.url || data.play || '';
  const kind =
    data.kind ||
    (data.type === 'embed' || playUrl.includes('embed') ? 'iframe' : 'hls');

  // Normalize server list
  let servers: StreamServer[] = [];
  if (Array.isArray(data.servers) && data.servers.length > 0) {
    servers = data.servers.map((s: any, idx: number) => ({
      label: s.label || `Server ${idx + 1}`,
      url: s.url,
      kind:
        s.kind ||
        (s.url?.includes('/proxy/hls') || s.url?.includes('.m3u8')
          ? 'hls'
          : 'iframe'),
    }));
  } else if (playUrl) {
    servers = [
      {
        label: 'Server 1 (Recommended)',
        url: playUrl,
        kind: kind === 'hls' ? 'hls' : 'iframe',
      },
    ];
  }

  return {
    kind: (servers[0]?.kind || kind) as 'hls' | 'iframe',
    url: servers[0]?.url || playUrl,
    servers,
    headers: data.headers,
    cached: Boolean(data.cached),
    type: data.type,
    play: playUrl,
    movie_id: Number(movieId),
    season: options.season,
    episode: options.episode,
  };
}

/**
 * Returns WebVTT subtitle track URL for the target movie ID.
 */
export function getSubtitleUrl(movieId: number | string): string {
  return `/api/subtitles/${movieId}`;
}

/**
 * Derives canonical content identifier matching Phase 3 Continue Watching schema.
 */
export function buildContentId(target: PlaybackTarget): string {
  if (target.isSeries) {
    const seriesId = target.canonicalSeriesId || target.id;
    const season = target.season ?? 1;
    const episode = target.episode ?? 1;
    return `series_${seriesId}_s${season}_e${episode}`;
  }
  return `movie_${target.id}`;
}

/**
 * Strips episode/season suffix from title to provide a clean display title.
 */
export function cleanTitle(title: string): string {
  return (title || '')
    .replace(/\s*[-·]\s*S\d+\s*E\d+.*$/i, '')
    .replace(/\s*\(\s*\d{4}\s*\)/i, '')
    .trim();
}

/**
 * Fetches the seasons and episodes tree for a series from GET /api/series/{movieId}/seasons.
 */
export async function getSeriesSeasons(
  movieId: number | string,
  signal?: AbortSignal
): Promise<SeriesSeasonResponse> {
  const res = await fetch(`/api/series/${movieId}/seasons`, {
    method: 'GET',
    credentials: 'include',
    signal,
  });

  if (!res.ok) {
    throw new Error(`Failed to load seasons hierarchy: ${res.status}`);
  }

  const data = await res.json();
  return {
    is_series: Boolean(data.is_series),
    title: data.title || '',
    current_season: Number(data.current_season) || 1,
    current_episode: Number(data.current_episode) || 1,
    seasons: Array.isArray(data.seasons) ? data.seasons : [],
    status: data.status,
    is_ended: Boolean(data.is_ended),
  };
}

/**
 * Derives verified next episode information based on actual ordered season/episode tree.
 */
export function getNextEpisodeInfo(
  currentSeason: number,
  currentEpisode: number,
  seriesData: SeriesSeasonResponse | null
): NextEpisodeInfo | null {
  if (!seriesData || !Array.isArray(seriesData.seasons) || seriesData.seasons.length === 0) {
    return null;
  }
  const curS = Number(currentSeason) || 1;
  const curE = Number(currentEpisode) || 1;

  // 1. Current season: look for next episode with episode_number > curE
  const curSeasonObj = seriesData.seasons.find((s) => Number(s.season_number) === curS);
  if (curSeasonObj && Array.isArray(curSeasonObj.episodes)) {
    const seasonEps = curSeasonObj.episodes
      .map((ep) => ({ ...ep, num: Number(ep.episode_number ?? ep.e) }))
      .filter((ep) => Number.isFinite(ep.num) && ep.num > 0)
      .sort((a, b) => a.num - b.num);

    const nextEp = seasonEps.find((ep) => ep.num > curE);
    if (nextEp) {
      const sPad = String(curS).padStart(2, '0');
      const ePad = String(nextEp.num).padStart(2, '0');
      const label = `S${sPad} E${ePad}`;
      return {
        hasNext: true,
        season: curS,
        episode: nextEp.num,
        movieId: nextEp.movie_id || null,
        name: nextEp.name || `Episode ${nextEp.num}`,
        label,
        fullTitle: `${label} · ${nextEp.name || `Episode ${nextEp.num}`}`,
        isFinalOfSeries: false,
      };
    }
  }

  // 2. Look for future seasons (season_number > curS)
  const futureSeasons = seriesData.seasons
    .map((s) => ({ ...s, sNum: Number(s.season_number) }))
    .filter((s) => Number.isFinite(s.sNum) && s.sNum > curS && s.sNum > 0)
    .sort((a, b) => a.sNum - b.sNum);

  for (const nextSeasonObj of futureSeasons) {
    if (Array.isArray(nextSeasonObj.episodes)) {
      const nextSeasonEps = nextSeasonObj.episodes
        .map((ep) => ({ ...ep, num: Number(ep.episode_number ?? ep.e) }))
        .filter((ep) => Number.isFinite(ep.num) && ep.num > 0)
        .sort((a, b) => a.num - b.num);

      if (nextSeasonEps.length > 0) {
        const firstEp = nextSeasonEps[0];
        const sPad = String(nextSeasonObj.sNum).padStart(2, '0');
        const ePad = String(firstEp.num).padStart(2, '0');
        const label = `S${sPad} E${ePad}`;
        return {
          hasNext: true,
          season: nextSeasonObj.sNum,
          episode: firstEp.num,
          movieId: firstEp.movie_id || null,
          name: firstEp.name || `Episode ${firstEp.num}`,
          label,
          fullTitle: `${label} · ${firstEp.name || `Episode ${firstEp.num}`}`,
          isFinalOfSeries: false,
        };
      }
    }
  }

  // 3. No next episode exists in current season and no future seasons exist.
  // This is definitively the final known episode of the series catalogue tree.
  const sPad = String(curS).padStart(2, '0');
  const ePad = String(curE).padStart(2, '0');
  return {
    hasNext: false,
    season: curS,
    episode: curE,
    movieId: null,
    name: '',
    label: `S${sPad} E${ePad}`,
    fullTitle: `S${sPad} E${ePad}`,
    isFinalOfSeries: true,
  };
}

/**
 * Calculates deterministic preview and automatic transition countdown thresholds
 * based on verified media duration:
 * - Long episodes (>= 600s / 10+ min): Preview at 180s, countdown at 15s.
 * - Medium episodes (300s to 599s, e.g. 5 min = 300s): Preview at min(180, 25% duration = 75s), countdown at 15s.
 * - Short episodes (< 300s, e.g. 120s = 2 min): Preview at 25% duration (30s for 120s), countdown at 8% duration (10s for 120s).
 */
export function getEpisodeTimingThresholds(duration: number | null | undefined): {
  previewThreshold: number;
  countdownThreshold: number;
} {
  if (!duration || !Number.isFinite(duration) || duration <= 0) {
    return { previewThreshold: 0, countdownThreshold: 0 };
  }
  if (duration >= 600) {
    return { previewThreshold: 180, countdownThreshold: 15 };
  }
  if (duration >= 300) {
    return {
      previewThreshold: Math.min(180, Math.floor(duration * 0.25)),
      countdownThreshold: 15,
    };
  }
  return {
    previewThreshold: Math.max(20, Math.round(duration * 0.25)),
    countdownThreshold: Math.max(5, Math.min(15, Math.round(duration * 0.08))),
  };
}

/**
 * Derives verified previous episode information based on actual ordered season/episode tree.
 */
export function getPreviousEpisodeInfo(
  currentSeason: number,
  currentEpisode: number,
  seriesData: SeriesSeasonResponse | null
): PreviousEpisodeInfo | null {
  if (!seriesData || !Array.isArray(seriesData.seasons) || seriesData.seasons.length === 0) {
    return null;
  }
  const curS = Number(currentSeason) || 1;
  const curE = Number(currentEpisode) || 1;

  // 1. Current season: find largest episode with num < curE
  const curSeasonObj = seriesData.seasons.find((s) => Number(s.season_number) === curS);
  if (curSeasonObj && Array.isArray(curSeasonObj.episodes)) {
    const seasonEps = curSeasonObj.episodes
      .map((ep) => ({ ...ep, num: Number(ep.episode_number ?? ep.e) }))
      .filter((ep) => Number.isFinite(ep.num) && ep.num > 0)
      .sort((a, b) => b.num - a.num); // Sort descending

    const prevEp = seasonEps.find((ep) => ep.num < curE);
    if (prevEp) {
      const sPad = String(curS).padStart(2, '0');
      const ePad = String(prevEp.num).padStart(2, '0');
      const label = `S${sPad} E${ePad}`;
      return {
        hasPrev: true,
        season: curS,
        episode: prevEp.num,
        movieId: prevEp.movie_id || null,
        name: prevEp.name || `Episode ${prevEp.num}`,
        label,
        fullTitle: `${label} · ${prevEp.name || `Episode ${prevEp.num}`}`,
      };
    }
  }

  // 2. Look for earlier seasons (season_number < curS)
  const earlierSeasons = seriesData.seasons
    .map((s) => ({ ...s, sNum: Number(s.season_number) }))
    .filter((s) => Number.isFinite(s.sNum) && s.sNum < curS && s.sNum > 0)
    .sort((a, b) => b.sNum - a.sNum); // Sort descending

  for (const prevSeasonObj of earlierSeasons) {
    if (Array.isArray(prevSeasonObj.episodes)) {
      const prevSeasonEps = prevSeasonObj.episodes
        .map((ep) => ({ ...ep, num: Number(ep.episode_number ?? ep.e) }))
        .filter((ep) => Number.isFinite(ep.num) && ep.num > 0)
        .sort((a, b) => b.num - a.num);

      if (prevSeasonEps.length > 0) {
        const lastEp = prevSeasonEps[0];
        const sPad = String(prevSeasonObj.sNum).padStart(2, '0');
        const ePad = String(lastEp.num).padStart(2, '0');
        const label = `S${sPad} E${ePad}`;
        return {
          hasPrev: true,
          season: prevSeasonObj.sNum,
          episode: lastEp.num,
          movieId: lastEp.movie_id || null,
          name: lastEp.name || `Episode ${lastEp.num}`,
          label,
          fullTitle: `${label} · ${lastEp.name || `Episode ${lastEp.num}`}`,
        };
      }
    }
  }

  return {
    hasPrev: false,
    season: curS,
    episode: curE,
    movieId: null,
    name: '',
    label: '',
    fullTitle: '',
  };
}


