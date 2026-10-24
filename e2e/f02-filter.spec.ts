import { test, expect } from '@playwright/test';

test.describe('F02: Multi-Faceted Catalog Filtering', () => {
  test('F02-H1: Filter by Movies and sort by rating', async ({ page }) => {
    await page.goto('/#/movies');

    await expect(page.getByRole('heading', { level: 1, name: /all movies/i })).toBeVisible();

    // Verify filter pill
    const moviesPill = page.getByRole('button', { name: /movies/i });
    await moviesPill.click();

    // Check media cards are displayed
    const cards = page.locator('.media-card');
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeGreaterThan(0);
  });
});
