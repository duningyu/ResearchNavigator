import { expect, test } from '@playwright/test';

const shareUrl = process.env.RN_PUBLIC_DEMO_SHARE_URL;
const frontendUrl = process.env.RN_PUBLIC_DEMO_FRONTEND_URL;
const demoEmail = process.env.RN_PUBLIC_DEMO_EMAIL;
const demoPassword = process.env.RN_PUBLIC_DEMO_PASSWORD;

test.describe('public demo naked frontend', () => {
  test.skip(!frontendUrl, 'Set RN_PUBLIC_DEMO_FRONTEND_URL to validate the deployed offline landing state.');

  test('shows a safe offline state without a tunnel URL', async ({ page }) => {
    const localRequests: string[] = [];
    page.on('request', (request) => {
      if (/^https?:\/\/(localhost|127\.0\.0\.1)(:|\/)/.test(request.url())) {
        localRequests.push(request.url());
      }
    });
    const response = await page.goto(frontendUrl!);
    expect(response?.ok()).toBe(true);
    await expect(page.getByRole('heading', { name: 'ResearchNavigator 演示当前离线' })).toBeVisible();
    await expect(page.getByTestId('backend-status')).toContainText('BACKEND_NOT_CONFIGURED');
    expect(localRequests).toEqual([]);
  });
});

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

    if (demoEmail && demoPassword) {
      await page.getByLabel('邮箱').fill(demoEmail);
      await page.getByLabel('密码').fill(demoPassword);
      const loginResponse = page.waitForResponse((response) => response.url().endsWith('/api/auth/login'));
      await page.getByRole('button', { name: /^登\s*录$/ }).click();
      await expect((await loginResponse).status()).toBe(200);
      await expect(page.getByRole('heading', { name: '今日研究起点' })).toBeVisible();

      await page.getByRole('menuitem', { name: /论文搜索$/ }).click();
      await page.getByPlaceholder(/关键词、题目、DOI/).fill('anomaly detection');
      await page.locator('#sources').click();
      await page.locator('.ant-select-item-option', { hasText: 'fixture' }).click();
      await page.getByRole('button', { name: /^搜\s*索$/ }).click();
      const firstResult = page.getByRole('link', { name: '证据级分析' }).first();
      await expect(firstResult).toBeVisible();
      await firstResult.click();
      await page.getByRole('button', { name: '收藏论文' }).click();
      await page.getByRole('menuitem', { name: /论文对比$/ }).click();
      await expect(page.getByText('生成证据级对比矩阵')).toBeVisible();
      await page.getByRole('menuitem', { name: /候选研究空白$/ }).click();
      await expect(page.getByText('生成候选研究空白', { exact: true })).toBeVisible();
    }

    expect(backendRequests.length).toBeGreaterThan(0);
    expect(backendRequests.every((url) => url.startsWith('https://'))).toBe(true);
  });
});
