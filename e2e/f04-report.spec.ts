import { test, expect } from '@playwright/test';

test.describe('F04: Report Broken Stream', () => {
  test('F04-H1: Open report modal and submit issue', async ({ page }) => {
    await page.goto('/#/movie/jawan');

    // Click report broken link button
    const reportBtn = page.getByRole('button', { name: /report broken link/i });
    await reportBtn.click();

    // Verify modal is visible
    const modal = page.locator('#modal-root');
    await expect(modal).toBeVisible();

    // Submit report
    const submitBtn = page.getByRole('button', { name: /submit issue report/i });
    await submitBtn.click();

    // Verify success toast
    const toast = page.locator('.toast-success');
    await expect(toast).toBeVisible();
  });
});
