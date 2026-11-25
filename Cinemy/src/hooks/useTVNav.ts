import { useEffect, useRef } from 'react';

export type Direction = 'up' | 'down' | 'left' | 'right';

const FOCUSABLE_SELECTOR = [
  'button:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  'a[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
].join(', ');

/**
 * Checks whether an element is visible and eligible for TV navigation.
 */
function isElementVisible(el: HTMLElement): boolean {
  if (!el || el.offsetParent === null && el.offsetWidth === 0 && el.offsetHeight === 0) {
    return false;
  }
  const style = window.getComputedStyle(el);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
    return false;
  }
  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

/**
 * Calculates spatial distance between the current active element and a candidate.
 * Applies directional penalties so elements strictly in the target direction are preferred.
 */
export function getSpatialFocusTarget(
  currentEl: HTMLElement,
  direction: Direction,
  scope?: HTMLElement
): HTMLElement | null {
  const root = scope || document.body;
  const rawCandidates = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
  const currentRect = currentEl.getBoundingClientRect();

  const cX = currentRect.left + currentRect.width / 2;
  const cY = currentRect.top + currentRect.height / 2;

  let bestTarget: HTMLElement | null = null;
  let minScore = Infinity;

  for (const candidate of rawCandidates) {
    if (candidate === currentEl || !isElementVisible(candidate)) {
      continue;
    }

    // Do not escape modal bounds if current element is inside a modal/overlay
    const activeOverlay = currentEl.closest<HTMLElement>('.prod-player-overlay, .modal-backdrop, [role="dialog"]');
    if (activeOverlay && !activeOverlay.contains(candidate)) {
      continue;
    }

    const tRect = candidate.getBoundingClientRect();
    const tX = tRect.left + tRect.width / 2;
    const tY = tRect.top + tRect.height / 2;

    const dx = tX - cX;
    const dy = tY - cY;

    // Check directional validity
    let isDirectionValid = false;
    let primaryDist = 0;
    let secondaryDist = 0;

    const tolX = Math.min(4, currentRect.width * 0.25);
    const tolY = Math.min(4, currentRect.height * 0.25);

    switch (direction) {
      case 'left':
        // Candidate must be strictly to the left (never match same-column vertical siblings)
        isDirectionValid = dx < -4 && (tRect.right <= currentRect.left + tolX || Math.abs(dx) >= Math.abs(dy));
        primaryDist = Math.abs(dx);
        secondaryDist = Math.abs(dy);
        break;
      case 'right':
        // Candidate must be strictly to the right (never match same-column vertical siblings)
        isDirectionValid = dx > 4 && (tRect.left >= currentRect.right - tolX || Math.abs(dx) >= Math.abs(dy));
        primaryDist = Math.abs(dx);
        secondaryDist = Math.abs(dy);
        break;
      case 'up':
        // Candidate must be strictly above (never match same-row horizontal siblings like 8px hero dots)
        isDirectionValid = dy < -4 && (tRect.bottom <= currentRect.top + tolY || Math.abs(dy) >= Math.abs(dx));
        primaryDist = Math.abs(dy);
        secondaryDist = Math.abs(dx);
        break;
      case 'down':
        // Candidate must be strictly below (never match same-row horizontal siblings like 8px hero dots)
        isDirectionValid = dy > 4 && (tRect.top >= currentRect.bottom - tolY || Math.abs(dy) >= Math.abs(dx));
        primaryDist = Math.abs(dy);
        secondaryDist = Math.abs(dx);
        break;
    }

    if (!isDirectionValid) continue;

    // Score: weighted sum of primary axis + secondary axis
    // Heavily penalize secondary axis misalignment
    const score = primaryDist + secondaryDist * 2.2;

    if (score < minScore) {
      minScore = score;
      bestTarget = candidate;
    }
  }

  return bestTarget;
}

export const TV_FOCUSED_CLASS = 'tv-remote-focused';

const INITIAL_FOCUS_SELECTOR =
  '.content-card, .cw-card, .btn-play-large, .btn-nav-back, .category-tab.active, .category-tab';

/**
 * Remove TV-remote visual focus marker from any previously focused element.
 */
export function clearTvFocus(): void {
  if (typeof document === 'undefined') return;
  document.querySelectorAll<HTMLElement>(`.${TV_FOCUSED_CLASS}`).forEach((el) => {
    el.classList.remove(TV_FOCUSED_CLASS);
  });
}

/**
 * Focus a target element for TV/remote navigation, apply a visible focus ring
 * (independent of browser :focus-visible untrusted-event heuristics), and scroll
 * both vertical page and horizontal row containers smoothly into view.
 */
export function applyTvFocus(target: HTMLElement): void {
  clearTvFocus();
  target.classList.add(TV_FOCUSED_CLASS);
  if (typeof target.focus === 'function') {
    try {
      target.focus({ preventScroll: true });
    } catch {
      target.focus();
    }
  }
  if (typeof target.scrollIntoView === 'function') {
    target.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
  }
}

function findInitialVisibleTarget(): HTMLElement | null {
  const candidates = Array.from(document.querySelectorAll<HTMLElement>(INITIAL_FOCUS_SELECTOR));
  for (const el of candidates) {
    if (isElementVisible(el)) {
      return el;
    }
  }
  return null;
}

/**
 * Activate the currently focused TV element (used by remote SELECT).
 * If nothing is focused yet, focuses the first visible interactive element first.
 */
export function activateFocusedTvElement(): boolean {
  if (typeof document === 'undefined') return false;
  const marked = document.querySelector<HTMLElement>(`.${TV_FOCUSED_CLASS}`);
  const active = document.activeElement as HTMLElement | null;
  const target =
    (marked && isElementVisible(marked) ? marked : null) ||
    (active && active !== document.body && active !== document.documentElement && isElementVisible(active)
      ? active
      : null);

  if (target) {
    target.click();
    return true;
  }

  const initial = findInitialVisibleTarget();
  if (initial) {
    applyTvFocus(initial);
    return true;
  }
  return false;
}

interface UseTVNavOptions {
  onBack?: () => void;
  isPlayerOpen?: boolean;
}

/**
 * Global Hook for Smart TV remote navigation (D-pad, Back / Escape, Input protection).
 */
export function useTVNav({ onBack, isPlayerOpen }: UseTVNavOptions = {}) {
  const lastActiveRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // If player overlay is open, let PlayerModal handle all remote/keyboard navigation (Vanilla L6214 parity)
      if (
        isPlayerOpen ||
        document.body.classList.contains('watch-page') ||
        document.querySelector('#overlay.on, .prod-player-overlay')
      ) {
        return;
      }

      // 1. Back / Escape Navigation
      if (
        e.key === 'Escape' ||
        e.key === 'GoBack' ||
        e.key === 'Back' ||
        (e as any).keyCode === 10009 // Tizen Back
      ) {
        // If a dropdown or search is open, let its local handler close it
        const searchInput = document.querySelector<HTMLInputElement>('.search-input');
        const searchDropdown = document.querySelector('.search-dropdown');
        if (searchDropdown && document.activeElement === searchInput) {
          // Handled by search input's onKeyDown
          return;
        }

        // Otherwise navigate back
        e.preventDefault();
        if (onBack) {
          onBack();
        } else if (typeof window !== 'undefined') {
          window.history.back();
        }
        return;
      }

      // 2. Input Protection: Never intercept arrow keys while typing in text inputs or textareas
      const active = document.activeElement as HTMLElement | null;
      if (
        active &&
        (active.tagName === 'INPUT' ||
          active.tagName === 'TEXTAREA' ||
          (active.tagName === 'SELECT' && (e.key === 'ArrowUp' || e.key === 'ArrowDown')))
      ) {
        // Let the input perform its default behavior / cursor / dropdown navigation
        return;
      }

      // 3. Arrow Keys Navigation (D-pad)
      let direction: Direction | null = null;
      switch (e.key) {
        case 'ArrowUp':
        case 'Up':
          direction = 'up';
          break;
        case 'ArrowDown':
        case 'Down':
          direction = 'down';
          break;
        case 'ArrowLeft':
        case 'Left':
          direction = 'left';
          break;
        case 'ArrowRight':
        case 'Right':
          direction = 'right';
          break;
      }

      if (!direction) return;

      // Determine starting element for spatial calculation
      let currentEl = active;
      if (!currentEl || currentEl === document.body || currentEl === document.documentElement) {
        const marked = document.querySelector<HTMLElement>(`.${TV_FOCUSED_CLASS}`);
        if (marked && isElementVisible(marked)) {
          currentEl = marked;
        } else {
          const initialTarget = findInitialVisibleTarget();
          if (initialTarget) {
            e.preventDefault();
            applyTvFocus(initialTarget);
            lastActiveRef.current = initialTarget;
            return;
          }
          return;
        }
      }

      const nextTarget = getSpatialFocusTarget(currentEl, direction);
      if (nextTarget) {
        e.preventDefault();
        applyTvFocus(nextTarget);
        lastActiveRef.current = nextTarget;
      }
    };

    const handlePointerDown = () => {
      clearTvFocus();
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('pointerdown', handlePointerDown, { passive: true });
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('pointerdown', handlePointerDown);
    };
  }, [onBack, isPlayerOpen]);

  return { lastActiveRef };
}

