// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { ContentCard } from '../ContentCard';
import { DiscoveryRow } from '../DiscoveryRow';
import { BrowseByYear } from '../BrowseByYear';
import { CatalogFilterBar } from '../CatalogFilterBar';
import { CategoryBar } from '../../layout/CategoryBar';
import type { MovieItem } from '../../../types/catalogue';

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
  });

  it('3. DiscoveryRow renders items and triggers onSeeAll', () => {
    const handleSeeAll = vi.fn();
    const handleSelectMovie = vi.fn();

    render(
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
});
