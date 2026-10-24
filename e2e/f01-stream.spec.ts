import { test, expect } from '@playwright/test';

test.describe('F01: Search, Select, and Stream a Movie', () => {
  test.beforeEach(async ({ page }) => {
    page.on('console', (msg) => {
      if (msg.type() === 'error') throw new Error(`Console error: ${msg.text()}`);
    });
    page.on('response', (res) => {
      if (res.status() >= 500) throw new Error(`${res.status()} on ${res.url()}`);
    });
  });

  test('F01-H1: Search for movie and start stream', async ({ page }) => {
    await page.goto('/');

    // 1. Search for Dune
    const searchInput = page.getByPlaceholder(/search movies/i);
    await searchInput.fill('dune');

    // 2. Select title from live autocomplete dropdown
    const resultItem = page.locator('.search-dropdown-item').first();
    await expect(resultItem).toBeVisible();
    await resultItem.click();

    // 3. Verify watch page loaded
    await expect(page.getByRole('heading', { level: 1, name: /dune: part two/i })).toBeVisible();

    // 4. Verify player is rendered and Server 1 is active
    const activeServer = page.getByRole('button', { name: /server 1/i });
    await expect(activeServer).toBeVisible();
    await expect(activeServer).toHaveClass(/active/);

    // 5. Test switching to Server 2
    const server2 = page.getByRole('button', { name: /server 2/i });
    await server2.click();
    await expect(server2).toHaveClass(/active/);
  });
});
