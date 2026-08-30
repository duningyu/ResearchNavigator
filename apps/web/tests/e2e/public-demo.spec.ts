import { expect, test } from '@playwright/test';

const shareUrl = process.env.RN_PUBLIC_DEMO_SHARE_URL;

test.describe('public demo deployment', () => {
  test.skip(!shareUrl, 'Set RN_PUBLIC_DEMO_SHARE_URL to run against a real Vercel + Quick Tunnel deployment.');

  test('loads the Vercel frontend and reaches the configured tunnel', async ({ page }) => {
    const backendRequests: string[] = [];
    page.on('request', (request) => {
      const url = request.url();
      if (url.includes('.trycloudflare.com')) backendRequests.push(url);
      expect(url).not.toMatch(/^https?:\/\/(localhost|127\.0\.0\.1)(:|\/)/);
    });
    await page.goto(shareUrl!);
    await expect(page).toHaveTitle(/ResearchNavigator/i);
    await expect(page.getByText(/登录|Login/i).first()).toBeVisible();
    expect(backendRequests.every((url) => url.startsWith('https://'))).toBe(true);
  });
});
