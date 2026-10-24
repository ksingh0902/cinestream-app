import { test, expect } from '@playwright/test';

test.describe('F03: TV Series Seasons and Episode Traversal', () => {
  test('F03-H1: Binge watch TV series episodes with Next button', async ({ page }) => {
    await page.goto('/#/series/stranger-things');

    await expect(page.getByRole('heading', { level: 1, name: /stranger things/i })).toBeVisible();

    // Click watch season 1 ep 1
    const watchEp1 = page.getByRole('link', { name: /watch season 1 ep 1/i });
    await watchEp1.click();

    // Verify episode watch page
    await expect(page.getByText(/episode 1/i)).toBeVisible();

    // Click Next Episode button
    const nextBtn = page.getByRole('link', { name: /next: ep 2/i });
    await expect(nextBtn).toBeVisible();
    await nextBtn.click();

    // Verify Episode 2 loaded
    await expect(page.getByText(/episode 2/i)).toBeVisible();
  });
});
