// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor } from '@testing-library/react';
import { ContentCard } from '../ContentCard';
import { DiscoveryRow } from '../DiscoveryRow';
import { BrowseByYear } from '../BrowseByYear';
import { CatalogFilterBar } from '../CatalogFilterBar';
import { FeaturedHero } from '../FeaturedHero';
import { CategoryBar } from '../../layout/CategoryBar';
import type { MovieItem } from '../../../types/catalogue';

vi.mock('../../../features/watchlist', () => ({
  useWatchlist: () => ({
    isInList: () => false,
    addItem: vi.fn(),
    removeItem: vi.fn(),
  }),
}));

const mockResolvePosterFallback = vi.fn().mockResolvedValue(null);
vi.mock('../../../api/catalogue', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/catalogue')>();
  return {
    ...actual,
    resolvePosterFallback: (...args: any[]) => mockResolvePosterFallback(...args),
  };
});

afterEach(() => {
  cleanup();
});

const mockMovie: MovieItem = {
  id: 101,
  title: 'Gladiator II',
  year: '2024',
  quality: 'HD',
  poster: 'https://example.com/poster.jpg',
  rating: 8.2,
  is_series: 0,
  genres: ['Action', 'Drama'],
  imdb: '8.2',
  source: 'yomovies',
  is_hindi_dubbed: false,
  upgradeBadge: 'CAM → HD',
};

describe('Discovery Components & Badging', () => {
  it('1. ContentCard renders upgrade badge correctly when present', () => {
    const handleSelect = vi.fn();
    const { container } = render(
      <ContentCard
        movie={mockMovie}
        onSelect={handleSelect}
        upgradeBadge="CAM → HD"
      />
    );

    const badge = container.querySelector('.card-badge-upgrade .badge-tag.upgrade');
    expect(badge).not.toBeNull();
    expect(badge?.textContent).toBe('CAM → HD');

    fireEvent.click(container.querySelector('.content-card')!);
    expect(handleSelect).toHaveBeenCalledWith(101, 'Gladiator II');
  });

  it('2. ContentCard hides upgrade badge when neither movie nor prop provides it', () => {
    const movieWithoutBadge: MovieItem = {
      ...mockMovie,
      is_hindi_dubbed: true,
      upgradeBadge: undefined,
      latest_quality_transition: undefined,
    };
    const { container } = render(
      <ContentCard
        movie={movieWithoutBadge}
        onSelect={vi.fn()}
      />
    );

    const badge = container.querySelector('.card-badge-upgrade');
    expect(badge).toBeNull();
    expect(container.querySelector('.badge-tag.dubbed')).toBeNull();
  });

  it('3. DiscoveryRow renders items and triggers onSeeAll', () => {
    const handleSeeAll = vi.fn();
    const handleSelectMovie = vi.fn();

    const { container } = render(
      <DiscoveryRow
        id="recently-added"
        title="Recently Added"
        count={1}
        items={[mockMovie]}
        onSelectMovie={handleSelectMovie}
        onSeeAll={handleSeeAll}
      />
    );

    expect(screen.getByText('Recently Added')).toBeDefined();
    expect(container.querySelector('.discovery-count-badge')).toBeNull();
    expect(screen.getByText('Gladiator II')).toBeDefined();

    const seeAllBtn = screen.getByText('See All');
    fireEvent.click(seeAllBtn);
    expect(handleSeeAll).toHaveBeenCalled();
  });

  it('4. DiscoveryRow renders empty state when items list is empty', () => {
    render(
      <DiscoveryRow
        id="empty-row"
        title="Recently Upgraded"
        count={0}
        items={[]}
        onSelectMovie={vi.fn()}
        emptyMessage="No titles recently upgraded"
      />
    );

    expect(screen.getByText('No titles recently upgraded')).toBeDefined();
  });

  it('5. BrowseByYear renders release year chips and handles click', () => {
    const handleSelectYear = vi.fn();
    const yearItems = [
      { year: '2026', count: 15 },
      { year: '2025', count: 240 },
      { year: '2024', count: 320 },
      { year: '2023', count: 410 },
    ];

    render(
      <BrowseByYear
        years={yearItems}
        olderCount={500}
        selectedYear="2025"
        onSelectYear={handleSelectYear}
      />
    );

    expect(screen.getByText('2026')).toBeDefined();
    expect(screen.getByText('2025')).toBeDefined();
    expect(screen.getByText('Older')).toBeDefined();

    fireEvent.click(screen.getByText('2024'));
    expect(handleSelectYear).toHaveBeenCalledWith('2024');

    fireEvent.click(screen.getByText('Older'));
    expect(handleSelectYear).toHaveBeenCalledWith('older');
  });

  it('6. CatalogFilterBar triggers filter updates', () => {
    const handleChangeFilter = vi.fn();
    const handleClear = vi.fn();
    render(
      <CatalogFilterBar
        filters={{ sort: 'first_added' }}
        onChangeFilter={handleChangeFilter}
        onClearFilters={handleClear}
      />
    );

    expect(screen.getByText('Filters')).toBeDefined();

    // Change sort select
    const selects = screen.getAllByRole('combobox');
    const sortSelect = selects.find((s) => (s as HTMLSelectElement).value === 'first_added');
    expect(sortSelect).toBeDefined();

    if (sortSelect) {
      fireEvent.change(sortSelect, { target: { value: 'year' } });
      expect(handleChangeFilter).toHaveBeenCalledWith('sort', 'year');
    }
  });

  it('7. CategoryBar triggers onSelectCategory with resetToken when All Titles is clicked', () => {
    const handleSelectCategory = vi.fn();
    render(
      <CategoryBar
        activeSelection={{ category: 'hindi-dubbed', genre: 'Hollywood Dubbed' }}
        onSelectCategory={handleSelectCategory}
      />
    );

    const allTitlesBtn = screen.getByText('All Titles');
    expect(allTitlesBtn).toBeDefined();

    fireEvent.click(allTitlesBtn);
    expect(handleSelectCategory).toHaveBeenCalledWith(
      expect.objectContaining({
        category: 'all',
        resetToken: expect.any(Number),
      })
    );
  });

  it('8. FeaturedHero supports touch swipe left/right to navigate slides on mobile', () => {
    vi.useFakeTimers();
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

    const secondMovie: MovieItem = { ...mockMovie, id: 102, title: 'Dune: Part Two', year: '2024' };
    const { container } = render(
      <FeaturedHero
        items={[mockMovie, secondMovie]}
        onPlay={vi.fn()}
        onMyList={vi.fn()}
      />
    );

    const hero = container.querySelector('.hero-fullbleed')!;
    expect(screen.getByRole('heading', { name: 'Gladiator II' })).toBeDefined();

    // Swipe left -> Next slide
    fireEvent.touchStart(hero, { touches: [{ clientX: 250, clientY: 200 }] });
    fireEvent.touchEnd(hero, { changedTouches: [{ clientX: 120, clientY: 205 }] });
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(screen.getByRole('heading', { name: 'Dune: Part Two' })).toBeDefined();

    // Swipe right -> Previous slide
    fireEvent.touchStart(hero, { touches: [{ clientX: 120, clientY: 200 }] });
    fireEvent.touchEnd(hero, { changedTouches: [{ clientX: 260, clientY: 205 }] });
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(screen.getByRole('heading', { name: 'Gladiator II' })).toBeDefined();

    vi.useRealTimers();
  });

  it('9. Trending Now and Recommended for You DiscoveryRows render titles cleanly', () => {
    const onSelect = vi.fn();
    render(
      <>
        <DiscoveryRow
          id="section-trending-now"
          title="Trending Now"
          count={1}
          items={[mockMovie]}
          onSelectMovie={onSelect}
        />
        <DiscoveryRow
          id="section-recommended-for-you"
          title="Recommended for You"
          count={1}
          items={[{ ...mockMovie, id: 202, title: 'Inception' }]}
          onSelectMovie={onSelect}
        />
      </>
    );

    expect(screen.getByText('Trending Now')).toBeDefined();
    expect(screen.getByText('Recommended for You')).toBeDefined();
    expect(screen.getByText('Gladiator II')).toBeDefined();
    expect(screen.getByText('Inception')).toBeDefined();
  });

  it('10. ContentCard poster lifecycle: valid poster transitions loading -> loaded', () => {
    const { container } = render(<ContentCard movie={mockMovie} onSelect={vi.fn()} />);
    const wrap = container.querySelector('.card-poster-wrap')!;
    const img = container.querySelector('.card-poster-img') as HTMLImageElement;

    expect(wrap.getAttribute('data-poster-state')).toBe('loading');
    expect(img.getAttribute('src')).toBe('https://example.com/poster.jpg');
    expect(img.getAttribute('loading')).toBe('lazy');

    fireEvent.load(img);
    expect(wrap.getAttribute('data-poster-state')).toBe('loaded');
    expect(img.getAttribute('src')).toBe('https://example.com/poster.jpg');
  });

  it('11. ContentCard poster recovery: 404 primary poster falls back to mirror poster_fallbacks and loads', () => {
    const movieWithFallback: MovieItem = {
      ...mockMovie,
      id: 11030,
      title: 'Spider-Man: Across the Spider-Verse (2023)',
      poster: 'https://m.media-amazon.com/images/M/broken-404.jpg',
      poster_fallbacks: ['https://image.tmdb.org/t/p/w500/8Vt6mWEReuy4Of61Lnj5Xj704m8.jpg'],
    };
    const { container } = render(<ContentCard movie={movieWithFallback} onSelect={vi.fn()} />);
    const wrap = container.querySelector('.card-poster-wrap')!;
    const img = container.querySelector('.card-poster-img') as HTMLImageElement;

    expect(img.getAttribute('src')).toBe('https://m.media-amazon.com/images/M/broken-404.jpg');
    expect(wrap.getAttribute('data-poster-state')).toBe('loading');

    fireEvent.error(img);
    expect(img.getAttribute('src')).toBe('https://image.tmdb.org/t/p/w500/8Vt6mWEReuy4Of61Lnj5Xj704m8.jpg');
    expect(wrap.getAttribute('data-poster-state')).toBe('loading');

    fireEvent.load(img);
    expect(wrap.getAttribute('data-poster-state')).toBe('loaded');
  });

  it('12. ContentCard permanent poster failure terminates loading and renders SVG fallback without looping', async () => {
    mockResolvePosterFallback.mockResolvedValueOnce(null);
    const brokenMovie: MovieItem = {
      ...mockMovie,
      id: 99999,
      poster: 'https://example.com/404.jpg',
      poster_fallbacks: [],
    };
    const { container } = render(<ContentCard movie={brokenMovie} onSelect={vi.fn()} />);
    const wrap = container.querySelector('.card-poster-wrap')!;
    const img = container.querySelector('.card-poster-img') as HTMLImageElement;

    fireEvent.error(img);
    await waitFor(() => {
      expect(wrap.getAttribute('data-poster-state')).toBe('error');
    });
    expect(img.getAttribute('src')).toContain('data:image/svg+xml');

    // Subsequent error must not re-enter loading state
    fireEvent.error(img);
    expect(wrap.getAttribute('data-poster-state')).toBe('error');
  });

  it('13. ContentCard resets poster state cleanly when poster URL prop changes', async () => {
    mockResolvePosterFallback.mockResolvedValueOnce(null);
    const movieA: MovieItem = { ...mockMovie, poster: 'https://example.com/a-broken.jpg' };
    const movieB: MovieItem = { ...mockMovie, poster: 'https://example.com/b-valid.jpg' };

    const { container, rerender } = render(<ContentCard movie={movieA} onSelect={vi.fn()} />);
    const wrap = container.querySelector('.card-poster-wrap')!;
    const img = container.querySelector('.card-poster-img') as HTMLImageElement;

    fireEvent.error(img);
    await waitFor(() => {
      expect(wrap.getAttribute('data-poster-state')).toBe('error');
    });

    rerender(<ContentCard movie={movieB} onSelect={vi.fn()} />);
    expect(wrap.getAttribute('data-poster-state')).toBe('loading');
    expect(img.getAttribute('src')).toBe('https://example.com/b-valid.jpg');

    fireEvent.load(img);
    expect(wrap.getAttribute('data-poster-state')).toBe('loaded');
  });

  it('14. Multiple ContentCards isolate poster errors from neighbouring cards', async () => {
    mockResolvePosterFallback.mockResolvedValueOnce(null);
    const brokenCard: MovieItem = { ...mockMovie, id: 501, title: 'Broken Card', poster: 'https://example.com/dead.jpg' };
    const healthyCard: MovieItem = { ...mockMovie, id: 502, title: 'Healthy Card', poster: 'https://example.com/ok.jpg' };

    const { container } = render(
      <>
        <ContentCard movie={brokenCard} onSelect={vi.fn()} />
        <ContentCard movie={healthyCard} onSelect={vi.fn()} />
      </>
    );

    const wraps = container.querySelectorAll('.card-poster-wrap');
    const imgs = container.querySelectorAll('.card-poster-img');

    fireEvent.error(imgs[0]);
    fireEvent.load(imgs[1]);

    await waitFor(() => {
      expect(wraps[0].getAttribute('data-poster-state')).toBe('error');
    });
    expect(wraps[1].getAttribute('data-poster-state')).toBe('loaded');
    expect(imgs[1].getAttribute('src')).toBe('https://example.com/ok.jpg');
  });

  it('15. Evergreen Picks DiscoveryRow renders up to 50 cards with Evergreen Picks heading', () => {
    const fiftyItems: MovieItem[] = Array.from({ length: 50 }, (_, idx) => ({
      ...mockMovie,
      id: 1000 + idx,
      title: `Evergreen Title ${idx + 1}`,
    }));
    const { container } = render(
      <DiscoveryRow
        id="section-recommended-for-you"
        title="Evergreen Picks"
        items={fiftyItems}
        onSelectMovie={vi.fn()}
      />
    );
    expect(screen.getByText('Evergreen Picks')).toBeDefined();
    expect(container.querySelectorAll('.content-card').length).toBe(50);
  });

  it('16. ContentCard recovers dead poster with no DB mirrors via bounded on-demand resolvePosterFallback', async () => {
    mockResolvePosterFallback.mockResolvedValueOnce('https://image.tmdb.org/t/p/w500/mastaney-live.jpg');
    const punjabiMovie: MovieItem = {
      ...mockMovie,
      id: 3492,
      title: 'Mastaney (2023) Punjabi',
      year: '2023',
      poster: 'https://m.media-amazon.com/images/M/dead-404.jpg',
      poster_fallbacks: [],
    };
    const { container } = render(<ContentCard movie={punjabiMovie} onSelect={vi.fn()} />);
    const wrap = container.querySelector('.card-poster-wrap')!;
    const img = container.querySelector('.card-poster-img') as HTMLImageElement;

    fireEvent.error(img);
    await waitFor(() => {
      expect(img.getAttribute('src')).toBe('https://image.tmdb.org/t/p/w500/mastaney-live.jpg');
    });
    fireEvent.load(img);
    expect(wrap.getAttribute('data-poster-state')).toBe('loaded');
  });
});
