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

let mockAuthUsername: string | null = 'viewer';
vi.mock('../../../context/AuthContext', () => ({
  useAuth: () => ({
    authenticated: Boolean(mockAuthUsername),
    username: mockAuthUsername,
    role: 'viewer',
    loading: false,
    error: null,
    isStorageOutage: false,
    refreshAuth: vi.fn(),
    logout: vi.fn(),
  }),
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
  mockAuthUsername = 'viewer';
  delete (window as any).IntersectionObserver;
  delete (globalThis as any).IntersectionObserver;
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
    expect(mockGetRecommended).toHaveBeenCalledWith({ limit: 18 });
    expect(mockGetTrending).toHaveBeenCalledTimes(1);
    expect(mockGetTrending).toHaveBeenCalledWith({ limit: 18 });
    expect(mockGetRecentlyAdded).toHaveBeenCalledTimes(1);
  });

  it('2. Recommended API failure gracefully falls back to GET /api/discovery/evergreen?limit=18', async () => {
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
    expect(mockGetEvergreen).toHaveBeenCalledWith({ limit: 18 });
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

describe('Recently Added: 5x15 See-All Grid + Source Priority Pagination', () => {
  const makeBatch = (startId: number, count: number) =>
    Array.from({ length: count }, (_, idx) => {
      const id = startId + idx;
      const src = id <= 10 ? 'yomovies' : idx % 2 === 0 ? 'dooflix' : 'ask4movie';
      return {
        ...mockMovie(id, `Recently Added Title ${id}`),
        source: src,
      };
    });

  it('1. Homepage Recently Added remains a limited horizontal row (limit=30), while See All loads 75 items in a 5-column grid and Load More appends the next 75', async () => {
    const page1Items = makeBatch(1, 75);
    const page2Items = makeBatch(76, 75);

    mockGetMovies.mockImplementation(({ sort, page, series }: { sort?: string; page?: number; series?: number }) => {
      if (sort === 'first_added') {
        if (page === 1) {
          return Promise.resolve({
            items: page1Items,
            total: 150,
            page: 1,
            per_page: 75,
            has_more: true,
          });
        }
        return Promise.resolve({
          items: page2Items,
          total: 150,
          page: 2,
          per_page: 75,
          has_more: false,
        });
      }
      return Promise.resolve({
        items: [mockMovie(series ? 2000 : 1000, series ? 'Sample Series' : 'Sample Movie', series ? 1 : 0)],
        total: 1,
        page: 1,
        per_page: 80,
        has_more: false,
      });
    });

    const { container } = render(
      <HomePage
        activeCategory={{ category: 'all' }}
        onResetCategory={vi.fn()}
        onSelectCategory={vi.fn()}
      />
    );

    // Homepage Recently Added stays a limited horizontal row
    await waitFor(() => {
      expect(mockGetRecentlyAdded).toHaveBeenCalledWith({
        limit: 18,
        window_months: 3,
        latest_crawl: true,
      });
    });
    expect(container.querySelector('#section-recently-added .discovery-row-track')).not.toBeNull();

    // Open Recently Added -> See All
    const seeAllBtn = screen.getByRole('button', { name: 'See All for Recently Added' });
    fireEvent.click(seeAllBtn);

    await waitFor(() => {
      expect(screen.getByText('Recently Added to CINEMY')).toBeDefined();
      expect(container.querySelectorAll('.content-grid--five-col .content-card').length).toBe(75);
    });

    const gridEl = container.querySelector('.content-grid--five-col');
    expect(gridEl?.getAttribute('data-columns')).toBe('5');
    expect(mockGetMovies).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, per_page: 75, sort: 'first_added' })
    );

    // Click Load More -> requests page 2 (per_page=75) and appends without replacing page 1
    const loadMoreBtn = screen.getByRole('button', { name: 'Load more movies and series' });
    fireEvent.click(loadMoreBtn);

    await waitFor(() => {
      expect(container.querySelectorAll('.content-grid--five-col .content-card').length).toBe(150);
    });

    expect(mockGetMovies).toHaveBeenCalledWith(
      expect.objectContaining({ page: 2, per_page: 75, sort: 'first_added' })
    );
    // Page 1 must NOT have been re-fetched when loading page 2
    const firstAddedPage1Calls = mockGetMovies.mock.calls.filter(
      ([arg]) => arg?.sort === 'first_added' && arg?.page === 1
    );
    expect(firstAddedPage1Calls.length).toBe(1);

    // Load More disappears when has_more is false
    expect(screen.queryByRole('button', { name: 'Load more movies and series' })).toBeNull();
    expect(screen.getByText(/You have viewed all 150 available titles/i)).toBeDefined();
  });

  it('2. Exactly 75 items with has_more=false renders all 75 cards and hides Load More', async () => {
    const exact75 = makeBatch(1, 75);
    mockGetMovies.mockImplementation(({ sort, series }: { sort?: string; series?: number }) => {
      if (sort === 'first_added') {
        return Promise.resolve({
          items: exact75,
          total: 75,
          page: 1,
          per_page: 75,
          has_more: false,
        });
      }
      return Promise.resolve({
        items: [mockMovie(series ? 2000 : 1000, series ? 'Sample Series' : 'Sample Movie', series ? 1 : 0)],
        total: 1,
        page: 1,
        per_page: 80,
        has_more: false,
      });
    });

    const { container } = render(
      <HomePage
        activeCategory={{ category: 'all' }}
        onResetCategory={vi.fn()}
        onSelectCategory={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'See All for Recently Added' })).toBeDefined();
    });
    fireEvent.click(screen.getByRole('button', { name: 'See All for Recently Added' }));

    await waitFor(() => {
      expect(container.querySelectorAll('.content-grid--five-col .content-card').length).toBe(75);
    });
    expect(screen.queryByRole('button', { name: 'Load more movies and series' })).toBeNull();
  });
});

describe('Progressive Home Lazy Loading (IntersectionObserver)', () => {
  type IOCallback = (entries: Array<{ isIntersecting: boolean; target: Element }>) => void;
  let observedMap: Map<Element, { cb: IOCallback; disconnect: ReturnType<typeof vi.fn> }>;

  function installMockIntersectionObserver() {
    observedMap = new Map();
    class MockIntersectionObserver {
      private cb: IOCallback;
      disconnect = vi.fn();
      constructor(cb: IOCallback) {
        this.cb = cb;
      }
      observe(el: Element) {
        observedMap.set(el, { cb: this.cb, disconnect: this.disconnect });
      }
      unobserve() {}
    }
    (window as any).IntersectionObserver = MockIntersectionObserver;
    (globalThis as any).IntersectionObserver = MockIntersectionObserver;
  }

  function triggerIntersection(sectionName: string, isIntersecting: boolean) {
    for (const [el, entry] of observedMap.entries()) {
      if (el.getAttribute('data-lazy-section') === sectionName) {
        entry.cb([{ isIntersecting, target: el }]);
      }
    }
  }

  it('1. Initial Home only fetches Priority 1 (Recently Added + Preferences) and does NOT fetch below-the-fold sections', async () => {
    installMockIntersectionObserver();

    render(
      <HomePage
        activeCategory={{ category: 'all' }}
        onResetCategory={vi.fn()}
        onSelectCategory={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getAllByText('Recent Film').length).toBeGreaterThan(0);
    });

    expect(mockGetRecentlyAdded).toHaveBeenCalledTimes(1);
    expect(mockGetRecentlyAdded).toHaveBeenCalledWith({
      limit: 18,
      window_months: 3,
      latest_crawl: true,
    });
    expect(mockGetHomepagePreferences).toHaveBeenCalledTimes(1);

    // Below-the-fold sections MUST NOT be fetched on initial mount
    expect(mockGetTrending).not.toHaveBeenCalled();
    expect(mockGetRecommended).not.toHaveBeenCalled();
    expect(mockGetEvergreen).not.toHaveBeenCalled();
    expect(mockGetRecentlyUpgraded).not.toHaveBeenCalled();
    expect(mockGetCatalogYears).not.toHaveBeenCalled();
    expect(mockGetMovies).not.toHaveBeenCalled();
  });

  it('2. Approaching a lazy section triggers exactly ONE request and re-entry does NOT duplicate', async () => {
    installMockIntersectionObserver();

    render(
      <HomePage
        activeCategory={{ category: 'all' }}
        onResetCategory={vi.fn()}
        onSelectCategory={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getAllByText('Recent Film').length).toBeGreaterThan(0);
    });

    // Approach Trending -> fetches once
    triggerIntersection('trending', true);
    await waitFor(() => {
      expect(screen.getByText('Trending Film')).toBeDefined();
    });
    expect(mockGetTrending).toHaveBeenCalledTimes(1);
    expect(mockGetTrending).toHaveBeenCalledWith({ limit: 18 });

    // Scroll away and re-enter -> MUST NOT fire again
    triggerIntersection('trending', false);
    triggerIntersection('trending', true);
    expect(mockGetTrending).toHaveBeenCalledTimes(1);

    // Approach Movies -> fetches per_page=36 once (not 80)
    triggerIntersection('movies', true);
    await waitFor(() => {
      expect(screen.getByText('Sample Movie')).toBeDefined();
    });
    expect(mockGetMovies).toHaveBeenCalledTimes(1);
    expect(mockGetMovies).toHaveBeenCalledWith({ per_page: 36, series: 0, sort: 'recent' });
  });

  it('3. Failed lazy section shows Retry without blocking other lazy sections', async () => {
    installMockIntersectionObserver();
    mockGetTrending.mockRejectedValueOnce(new Error('Trending timeout'));

    render(
      <HomePage
        activeCategory={{ category: 'all' }}
        onResetCategory={vi.fn()}
        onSelectCategory={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getAllByText('Recent Film').length).toBeGreaterThan(0);
    });

    triggerIntersection('trending', true);
    triggerIntersection('evergreen', true);

    await waitFor(() => {
      expect(screen.getByText('Trending timeout')).toBeDefined();
      expect(screen.getByText('Evergreen Classic')).toBeDefined();
    });

    mockGetTrending.mockResolvedValueOnce({
      items: [mockMovie(99, 'Trending Recovered')],
      total: 1,
      mode: 'fallback_trending',
      is_fallback: true,
    });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => {
      expect(screen.getByText('Trending Recovered')).toBeDefined();
    });
  });

  it('4. Viewer change clears personalized Recommended state so data never leaks across viewers', async () => {
    installMockIntersectionObserver();
    mockGetRecommended.mockResolvedValueOnce({
      items: [mockMovie(301, 'Viewer A Rec')],
      total: 1,
      personalized: true,
      mode: 'personalized',
    });

    const { rerender } = render(
      <HomePage
        activeCategory={{ category: 'all' }}
        onResetCategory={vi.fn()}
        onSelectCategory={vi.fn()}
      />
    );

    triggerIntersection('evergreen', true);
    await waitFor(() => {
      expect(screen.getByText('Viewer A Rec')).toBeDefined();
    });

    // Switch authenticated viewer to Viewer B (same mounted HomePage, no manual reset needed)
    mockAuthUsername = 'viewer_b';
    mockGetRecommended.mockResolvedValueOnce({
      items: [mockMovie(302, 'Viewer B Rec')],
      total: 1,
      personalized: true,
      mode: 'personalized',
    });

    rerender(
      <HomePage
        activeCategory={{ category: 'all' }}
        onResetCategory={vi.fn()}
        onSelectCategory={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Viewer B Rec')).toBeDefined();
    });
    expect(screen.queryByText('Viewer A Rec')).toBeNull();
  });
});
