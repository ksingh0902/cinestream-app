import { test, expect } from '@playwright/test';

test.describe('F05: Save Title to Watchlist', () => {
  test('F05-H1: Bookmark movie and view in watchlist page', async ({ page }) => {
    await page.goto('/');

    // Check initial badge
    const badge = page.locator('#watchlist-count');
    await expect(badge).toHaveText('0');

    // Click bookmark button on featured hero
    const bookmarkBtn = page.getByRole('button', { name: /add to watchlist/i }).first();
    await bookmarkBtn.click();

    // Verify counter updated
    await expect(badge).toHaveText('1');

    // Navigate to Watchlist
    await page.goto('/#/watchlist');
    await expect(page.getByRole('heading', { name: /my saved watchlist/i })).toBeVisible();

    const savedCards = page.locator('.media-card');
    await expect(savedCards.first()).toBeVisible();
  });
});
