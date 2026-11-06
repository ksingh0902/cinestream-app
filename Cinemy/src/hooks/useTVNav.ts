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

    switch (direction) {
      case 'left':
        // Candidate center or right edge must be to the left of current center
        isDirectionValid = tRect.right <= currentRect.left + 8 || dx < -4;
        primaryDist = Math.abs(dx);
        secondaryDist = Math.abs(dy);
        break;
      case 'right':
        isDirectionValid = tRect.left >= currentRect.right - 8 || dx > 4;
        primaryDist = Math.abs(dx);
        secondaryDist = Math.abs(dy);
        break;
      case 'up':
        isDirectionValid = tRect.bottom <= currentRect.top + 8 || dy < -4;
        primaryDist = Math.abs(dy);
        secondaryDist = Math.abs(dx);
        break;
      case 'down':
        isDirectionValid = tRect.top >= currentRect.bottom - 8 || dy > 4;
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

        // If player modal is open, let PlayerModal handle its close
        if (isPlayerOpen || document.querySelector('.prod-player-overlay')) {
          // Handled by PlayerModal
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
        // Find first sensible focus target
        const initialTarget = document.querySelector<HTMLElement>(
          '.category-tab.active, .category-tab, .btn-nav-back, .btn-play-large, .content-card'
        );
        if (initialTarget && isElementVisible(initialTarget)) {
          e.preventDefault();
          initialTarget.focus();
          initialTarget.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
          return;
        }
        return;
      }

      const nextTarget = getSpatialFocusTarget(currentEl, direction);
      if (nextTarget) {
        e.preventDefault();
        nextTarget.focus();
        nextTarget.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onBack, isPlayerOpen]);

  return { lastActiveRef };
}

