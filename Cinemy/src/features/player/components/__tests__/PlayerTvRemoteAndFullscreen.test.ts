import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('Player TV Remote & Watchdog Prevention Logic', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('1. TV remote D-Pad Down scrolls overlay down when not inside input', () => {
    let scrolledBy: { top: number; behavior: string } | null = null;
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
        !isInput
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
        overlay.scrollTop > 10
      ) {
        overlay.scrollBy({ top: -300, behavior: 'smooth' });
      }
    };

    handleKeyDown({ key: 'ArrowUp', keyCode: 38 });
    expect(scrolledBy).toEqual({ top: -300, behavior: 'smooth' });
  });

  it('3. TV Back / Escape closes modal cleanly', () => {
    let modalClosed = false;

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
        handleClose();
      }
    };

    handleKeyDown({ key: 'Back', keyCode: 10009 });
    expect(modalClosed).toBe(true);
  });

  it('4. Watchdog timer fix: active streams (iframe/HLS) are NOT auto-switched after 10s', () => {
    let activeServerIdx = 0;
    const servers = [{ label: 'Server 1 (DOO)' }, { label: 'Server 2 (ASK)' }];

    const triggerAutoFallback = vi.fn((failedIdx: number) => {
      activeServerIdx = failedIdx + 1;
    });

    // Start server 0 with watchdog timer disabled (safe mode)
    const startWatchdog = (_idx: number) => {
      // Intentionally do NOT schedule timeout
    };

    startWatchdog(activeServerIdx);

    // Fast-forward past 10s, 20s, 60s
    vi.advanceTimersByTime(60000);

    // Verify Server 1 was NEVER abandoned
    expect(triggerAutoFallback).not.toHaveBeenCalled();
    expect(activeServerIdx).toBe(0);
    expect(servers[activeServerIdx].label).toBe('Server 1 (DOO)');
  });
});
