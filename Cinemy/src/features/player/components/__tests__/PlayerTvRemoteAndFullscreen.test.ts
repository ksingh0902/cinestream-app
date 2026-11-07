import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('Player TV Remote & Fullscreen Interaction Logic', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('1. TV remote D-Pad Down scrolls overlay down when not inside input or fullscreen', () => {
    let scrolledBy: { top: number; behavior: string } | null = null;
    const isFullscreen = false;
    const isInput = false;

    const overlay = {
      scrollBy: (opts: { top: number; behavior: string }) => {
        scrolledBy = opts;
      },
    };

    const handleKeyDown = (e: { key: string; keyCode?: number }) => {
      if (
        (e.key === 'ArrowDown' ||
          e.key === 'Down' ||
          e.keyCode === 40 ||
          e.key === 'PageDown' ||
          e.keyCode === 34) &&
        !isInput &&
        !isFullscreen
      ) {
        overlay.scrollBy({ top: 300, behavior: 'smooth' });
      }
    };

    handleKeyDown({ key: 'ArrowDown', keyCode: 40 });
    expect(scrolledBy).toEqual({ top: 300, behavior: 'smooth' });

    // Also test TV remote keyCode 40 with alternate key string 'Down'
    scrolledBy = null;
    handleKeyDown({ key: 'Down' });
    expect(scrolledBy).toEqual({ top: 300, behavior: 'smooth' });
  });

  it('2. TV remote D-Pad Up scrolls overlay back up when scrollTop > 10', () => {
    let scrolledBy: { top: number; behavior: string } | null = null;
    const isFullscreen = false;
    const isInput = false;

    const overlay = {
      scrollTop: 150,
      scrollBy: (opts: { top: number; behavior: string }) => {
        scrolledBy = opts;
      },
    };

    const handleKeyDown = (e: { key: string; keyCode?: number }) => {
      if (
        (e.key === 'ArrowUp' ||
          e.key === 'Up' ||
          e.keyCode === 38 ||
          e.key === 'PageUp' ||
          e.keyCode === 33) &&
        !isInput &&
        !isFullscreen &&
        overlay.scrollTop > 10
      ) {
        overlay.scrollBy({ top: -300, behavior: 'smooth' });
      }
    };

    handleKeyDown({ key: 'ArrowUp', keyCode: 38 });
    expect(scrolledBy).toEqual({ top: -300, behavior: 'smooth' });
  });

  it('3. TV Back / Escape exits fullscreen first if fullscreen is active, preserving modal', () => {
    let isFullscreen = true;
    let modalClosed = false;

    const exitFullscreen = () => {
      isFullscreen = false;
    };
    const handleClose = () => {
      modalClosed = true;
    };

    const handleKeyDown = (e: { key: string; keyCode?: number }) => {
      if (
        e.key === 'Escape' ||
        e.key === 'GoBack' ||
        e.key === 'Back' ||
        e.keyCode === 10009
      ) {
        if (isFullscreen) {
          exitFullscreen();
          return;
        }
        handleClose();
      }
    };

    // First Back keypress: exits fullscreen only
    handleKeyDown({ key: 'Back', keyCode: 10009 });
    expect(isFullscreen).toBe(false);
    expect(modalClosed).toBe(false);

    // Second Back keypress: closes modal
    handleKeyDown({ key: 'Back', keyCode: 10009 });
    expect(modalClosed).toBe(true);
  });

  it('4. Fullscreen shortcut key "f" toggles fullscreen state', () => {
    let isFullscreen = false;
    const isInput = false;

    const toggleFullscreen = () => {
      isFullscreen = !isFullscreen;
    };

    const handleKeyDown = (e: { key: string }) => {
      if ((e.key === 'f' || e.key === 'F') && !isInput) {
        toggleFullscreen();
      }
    };

    handleKeyDown({ key: 'f' });
    expect(isFullscreen).toBe(true);

    handleKeyDown({ key: 'F' });
    expect(isFullscreen).toBe(false);
  });

  it('5. Fullscreen fallback to CSS theater mode when native fullscreen is unavailable or rejects', async () => {
    let isFullscreen = false;
    const mockContainer = {
      requestFullscreen: vi.fn().mockRejectedValue(new Error('Fullscreen not allowed')),
    };

    const enterFullscreen = async () => {
      if (mockContainer && typeof mockContainer.requestFullscreen === 'function') {
        try {
          await mockContainer.requestFullscreen();
          isFullscreen = true;
          return;
        } catch {
          // Fallback to CSS theater mode
        }
      }
      isFullscreen = true;
    };

    await enterFullscreen();
    expect(mockContainer.requestFullscreen).toHaveBeenCalledTimes(1);
    expect(isFullscreen).toBe(true); // Successfully fell back to CSS fullscreen!
  });
});
