// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { HomePage } from '../HomePage';
import { request } from '../../../api/client';
import { ApiError } from '../../../api/types';
import type { MovieItem } from '../../../types/catalogue';

const mockNavigate = vi.fn();
vi.mock('../../../router', () => ({
  useRouter: () => ({ navigate: mockNavigate }),
}));

vi.mock('../../../features/watchlist', () => ({
  useWatchlist: () => ({
    items: [{ id: 999, title: 'Saved On WAP' }],
    itemCount: 1,
    isInList: () => false,
    addItem: vi.fn(),
    removeItem: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock('../../../features/continue-watching', () => ({
  ContinueWatchingSection: () => <div data-testid="cw-section">Continue Watching Mock</div>,
}));

vi.mock('../../../features/player', () => ({
  PlayerModal: () => null,
}));

const mockMovie = (id: number, title: string, is_series = 0): MovieItem => ({
  id,
  title,
  year: '2024',
  poster: 'https://example.com/poster.jpg',
  rating: 8.5,
  imdb: '8.5',
  quality: '1080p',
  genres: ['Drama'],
  is_series,
  source: 'yomovies',
  is_hindi_dubbed: false,
});

const mockGetRecentlyAdded = vi.fn();
const mockGetRecentlyUpgraded = vi.fn();
const mockGetTrending = vi.fn();
const mockGetRecommended = vi.fn();
const mockGetEvergreen = vi.fn();
const mockGetCatalogYears = vi.fn();
const mockGetMovies = vi.fn();
const mockGetHomepagePreferences = vi.fn();

vi.mock('../../../api/catalogue', () => ({
  getRecentlyAdded: (...args: any[]) => mockGetRecentlyAdded(...args),
  getRecentlyUpgraded: (...args: any[]) => mockGetRecentlyUpgraded(...args),
  getTrending: (...args: any[]) => mockGetTrending(...args),
  getRecommended: (...args: any[]) => mockGetRecommended(...args),
  getEvergreen: (...args: any[]) => mockGetEvergreen(...args),
  getCatalogYears: (...args: any[]) => mockGetCatalogYears(...args),
  getMovies: (...args: any[]) => mockGetMovies(...args),
  getHomepagePreferences: (...args: any[]) => mockGetHomepagePreferences(...args),
  resolvePosterFallback: vi.fn().mockResolvedValue(null),
}));

beforeEach(() => {
  vi.clearAllMocks();
  if (!window.matchMedia) {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  }
  mockGetHomepagePreferences.mockResolvedValue({
    recently_added_enabled: true,
    recently_upgraded_enabled: true,
    recently_added_window_months: 3,
    recently_upgraded_window_months: 3,
    default_sort: 'recent',
    allowed_qualities: ['4K', '1080p', '720p', 'HD'],
  });
  mockGetRecentlyAdded.mockResolvedValue({ items: [mockMovie(1, 'Recent Film')], total: 1, window_months: 3 });
  mockGetRecentlyUpgraded.mockResolvedValue({ items: [], total: 0, window_months: 3 });
  mockGetTrending.mockResolvedValue({ items: [mockMovie(2, 'Trending Film')], total: 1, mode: 'fallback_trending', is_fallback: true });
  mockGetRecommended.mockResolvedValue({
    items: [mockMovie(3, 'Evergreen Classic')],
    total: 1,
    personalized: false,
    mode: 'evergreen_fallback',
  });
  mockGetEvergreen.mockResolvedValue({
    items: [mockMovie(4, 'Direct Evergreen Fallback')],
    total: 1,
    mode: 'evergreen_picks',
  });
  mockGetCatalogYears.mockResolvedValue({ years: [{ year: '2026', count: 10 }], older_count: 100 });
  mockGetMovies.mockImplementation(({ series }: { series?: number }) =>
    Promise.resolve({
      items: [mockMovie(series ? 20 : 10, series ? 'Sample Series' : 'Sample Movie', series ? 1 : 0)],
      total: 1,
      page: 1,
      per_page: 80,
      has_more: false,
    })
  );
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('Workstream A & B: Cross-Platform Discovery Consistency + Independent Loading', () => {
  it('1. Option A: HomePage calls getRecommended without device-local seed_ids, renders Evergreen Picks, and fires only ONE fetch wave', async () => {
    render(
      <HomePage
        activeCategory={{ category: 'all' }}
        onResetCategory={vi.fn()}
        onSelectCategory={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Evergreen Picks')).toBeDefined();
      expect(screen.getByText('Evergreen Classic')).toBeDefined();
    });

    // Must never send device-local seed_ids from watchlist/continue-watching
    expect(mockGetRecommended).toHaveBeenCalledTimes(1);
    expect(mockGetRecommended).toHaveBeenCalledWith({ limit: 50 });
    expect(mockGetTrending).toHaveBeenCalledTimes(1);
    expect(mockGetTrending).toHaveBeenCalledWith({ limit: 50 });
    expect(mockGetRecentlyAdded).toHaveBeenCalledTimes(1);
  });

  it('2. Recommended API failure gracefully falls back to GET /api/discovery/evergreen?limit=50', async () => {
    mockGetRecommended.mockRejectedValueOnce(new Error('500 Internal Server Error'));

    render(
      <HomePage
        activeCategory={{ category: 'all' }}
        onResetCategory={vi.fn()}
        onSelectCategory={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Evergreen Picks')).toBeDefined();
      expect(screen.getByText('Direct Evergreen Fallback')).toBeDefined();
    });
    expect(mockGetEvergreen).toHaveBeenCalledWith({ limit: 50 });
  });

  it('3. Independent loading: Trending failure does not block Recently Added, Evergreen Picks, Movies, or Series', async () => {
    mockGetTrending.mockRejectedValueOnce(new Error('Request timed out. Please try again.'));

    render(
      <HomePage
        activeCategory={{ category: 'all' }}
        onResetCategory={vi.fn()}
        onSelectCategory={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getAllByText('Recent Film').length).toBeGreaterThan(0);
      expect(screen.getByText('Evergreen Classic')).toBeDefined();
      expect(screen.getByText('Sample Movie')).toBeDefined();
      expect(screen.getByText('Sample Series')).toBeDefined();
      expect(screen.getByText('Request timed out. Please try again.')).toBeDefined();
    });

    // Clicking section Retry recovers Trending Now
    mockGetTrending.mockResolvedValueOnce({
      items: [mockMovie(22, 'Recovered Trending')],
      total: 1,
      mode: 'fallback_trending',
      is_fallback: true,
    });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => {
      expect(screen.getByText('Recovered Trending')).toBeDefined();
    });
  });

  it('4. Both Recommended and Evergreen failing shows graceful section error state without hiding or freezing the page', async () => {
    mockGetRecommended.mockRejectedValueOnce(new Error('Recommended down'));
    mockGetEvergreen.mockRejectedValueOnce(new Error('Evergreen down'));

    render(
      <HomePage
        activeCategory={{ category: 'all' }}
        onResetCategory={vi.fn()}
        onSelectCategory={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Evergreen down')).toBeDefined();
      expect(screen.getByText('Trending Film')).toBeDefined();
    });
  });

  it('5. apiClient request enforces bounded AbortController timeout and distinguishes timeout vs caller abort', async () => {
    vi.useFakeTimers();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((_url, init) => {
      return new Promise((_resolve, reject) => {
        const sig = (init as RequestInit | undefined)?.signal;
        sig?.addEventListener('abort', () => {
          const err = new Error('Aborted');
          err.name = 'AbortError';
          reject(err);
        });
      });
    });

    const p = request('/api/slow-endpoint', { timeoutMs: 100 });
    vi.advanceTimersByTime(120);

    await expect(p).rejects.toSatisfy((err: unknown) => {
      return err instanceof ApiError && err.isTimeout === true && err.status === 408;
    });

    // Caller-initiated abort is distinguished from timeout
    const callerCtrl = new AbortController();
    const p2 = request('/api/cancel-me', { timeoutMs: 15000, signal: callerCtrl.signal });
    callerCtrl.abort();

    await expect(p2).rejects.toSatisfy((err: unknown) => {
      return err instanceof ApiError && err.isAborted === true && err.isTimeout === false;
    });

    fetchSpy.mockRestore();
  });
});
