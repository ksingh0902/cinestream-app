import { StoredControllerAuth, StoredTvIdentity } from './types';

export type DeviceRole = 'tv' | 'phone';

const SMART_TV_UA_RE =
  /\b(tizen|web0s|webos|smart-?tv|smarttv|googletv|android tv|aft[a-z0-9]+|bravia|viera|netcast|hbbtv|roku|crkey|xbox|playstation)\b/i;

export function isSmartTvUserAgent(uaOverride?: string): boolean {
  if (uaOverride !== undefined) {
    return SMART_TV_UA_RE.test(uaOverride);
  }
  const w = typeof window !== 'undefined' ? (window as any) : null;
  if (w?.tizen?.tvinputdevice || w?.webOS) return true;
  if (typeof navigator === 'undefined') return false;
  return SMART_TV_UA_RE.test(navigator.userAgent || '');
}

export function isMobilePhoneUserAgent(uaOverride?: string): boolean {
  const ua =
    uaOverride !== undefined
      ? uaOverride
      : typeof navigator !== 'undefined'
        ? navigator.userAgent || ''
        : '';
  if (!ua || SMART_TV_UA_RE.test(ua)) return false;
  if (/\b(iphone|ipod|windows phone|blackberry|bb10)\b/i.test(ua)) return true;
  if (/\bandroid\b/i.test(ua) && /\bmobile\b/i.test(ua)) return true;
  return false;
}

function hasStoredPhoneController(
  controllerState?: StoredControllerAuth | Record<string, StoredControllerAuth> | null
): boolean {
  if (!controllerState) return false;
  if ('controllerId' in controllerState && typeof controllerState.controllerId === 'string') {
    return Boolean(controllerState.controllerId && controllerState.tvId);
  }
  return Object.keys(controllerState).length > 0;
}

/**
 * Authoritative device role resolution (never relies on window.innerWidth, CSS media queries, or IP):
 *  1. Explicit Smart TV runtime / UA -> 'tv'
 *  2. Active/stored phone controller -> 'phone' (overrides any stale TV identity)
 *  3. Mobile phone UA -> 'phone'
 *  4. Stored TV identity (e.g., desktop browser registered as TV) -> 'tv'
 *  5. Otherwise -> 'phone'
 */
export function resolveDeviceRole(
  tvIdentity: StoredTvIdentity | null,
  controllerState?: StoredControllerAuth | Record<string, StoredControllerAuth> | null,
  uaOverride?: string
): DeviceRole {
  if (isSmartTvUserAgent(uaOverride)) return 'tv';
  if (hasStoredPhoneController(controllerState)) return 'phone';
  if (isMobilePhoneUserAgent(uaOverride)) return 'phone';
  if (tvIdentity && tvIdentity.tvId) return 'tv';
  return 'phone';
}

const TV_IDENTITY_KEY = 'cinemy_tv_identity_v1';
const PHONE_CONTROLLERS_KEY = 'cinemy_tv_controllers_v1';
const ACTIVE_TV_KEY = 'cinemy_active_remote_tv_v1';

export function readStoredTvIdentity(): StoredTvIdentity | null {
  try {
    const raw = localStorage.getItem(TV_IDENTITY_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.tvId === 'string' && typeof parsed.deviceSecret === 'string') {
      return {
        tvId: parsed.tvId,
        name: typeof parsed.name === 'string' && parsed.name.trim() ? parsed.name : 'Living Room TV',
        deviceSecret: parsed.deviceSecret,
      };
    }
    return null;
  } catch {
    return null;
  }
}

export function saveStoredTvIdentity(identity: StoredTvIdentity): void {
  try {
    localStorage.setItem(TV_IDENTITY_KEY, JSON.stringify(identity));
  } catch {
    // Ignore storage quota / private mode failures
  }
}

export function clearStoredTvIdentity(): void {
  try {
    localStorage.removeItem(TV_IDENTITY_KEY);
  } catch {
    // Ignore
  }
}

export function readStoredControllers(): Record<string, StoredControllerAuth> {
  try {
    const raw = localStorage.getItem(PHONE_CONTROLLERS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

export function saveStoredController(auth: StoredControllerAuth): void {
  try {
    const all = readStoredControllers();
    all[auth.tvId] = auth;
    localStorage.setItem(PHONE_CONTROLLERS_KEY, JSON.stringify(all));
    localStorage.setItem(ACTIVE_TV_KEY, auth.tvId);
    // Clear any stale TV registration once this browser pairs as a phone controller
    clearStoredTvIdentity();
  } catch {
    // Ignore
  }
}

export function removeStoredController(tvId: string): void {
  try {
    const all = readStoredControllers();
    delete all[tvId];
    localStorage.setItem(PHONE_CONTROLLERS_KEY, JSON.stringify(all));
    if (localStorage.getItem(ACTIVE_TV_KEY) === tvId) {
      const remaining = Object.keys(all);
      if (remaining.length > 0) {
        localStorage.setItem(ACTIVE_TV_KEY, remaining[0]);
      } else {
        localStorage.removeItem(ACTIVE_TV_KEY);
      }
    }
  } catch {
    // Ignore
  }
}

export function readActiveRemoteTvId(): string | null {
  try {
    return localStorage.getItem(ACTIVE_TV_KEY);
  } catch {
    return null;
  }
}

export function saveActiveRemoteTvId(tvId: string | null): void {
  try {
    if (tvId) {
      localStorage.setItem(ACTIVE_TV_KEY, tvId);
    } else {
      localStorage.removeItem(ACTIVE_TV_KEY);
    }
  } catch {
    // Ignore
  }
}
