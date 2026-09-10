import { expect, test, type Page } from '@playwright/test';

async function register(page: Page, email: string) {
  await page.goto('/');
  await page.getByText('注册').click();
  await page.getByLabel('姓名').fill('UX-001 Anchor User');
  await page.getByLabel('邮箱').fill(email);
  await page.getByLabel('密码').fill('e2e-research-pass-123');
  await page.getByRole('button', { name: '创建账户' }).click();
  await expect(page.getByRole('heading', { name: '今日研究起点' })).toBeVisible();
}

async function selectFixtureSource(page: Page) {
  await page.locator('#sources').click();
  const option = page.getByText('本地示例（非真实检索）', { exact: true }).last();
  await option.click();
}

test('UX-001 restores the selected result anchor into the viewport after detail return', async ({ page }) => {
  const suffix = Date.now();
  await register(page, `ux001-anchor-${suffix}@example.com`);

  await page.goto('/projects');
  await page.getByRole('button', { name: '新建研究项目' }).click();
  const projectName = `UX-001 anchor project ${suffix}`;
  await page.getByLabel('项目名称').fill(projectName);
  await page.getByLabel('研究方向').fill('工业时序异常检测');
  await page.getByRole('button', { name: /^创\s*建$/ }).click();
  await expect(page.getByText(projectName)).toBeVisible();

  await page.getByRole('menuitem', { name: /找论文$/ }).click();
  await page.getByPlaceholder(/关键词、题目、DOI/).fill('anomaly detection');
  await selectFixtureSource(page);

  let searchPosts = 0;
  const onRequest = (request: import('@playwright/test').Request) => {
    if (request.url().includes('/search/papers') && request.method() === 'POST') searchPosts += 1;
  };
  page.on('request', onRequest);
  await page.getByRole('button', { name: /^搜\s*索$/ }).click();
  await expect(page.getByText(/本地示例（非真实检索）.*已响应/)).toBeVisible();
  await expect(page.locator('[data-search-paper]')).toHaveCount(10);

  const nextPage = page.locator('li[title="Next Page"] button');
  await expect(nextPage).toBeEnabled();
  await nextPage.click();
  await nextPage.click();
  const rows = page.locator('[data-search-paper]');
  await expect(rows).toHaveCount(10);
  const target = rows.last();
  const targetId = await target.getAttribute('data-search-paper');
  expect(targetId).toBeTruthy();
  const detailLink = target.getByRole('link', { name: '查看论文与证据' });
  await detailLink.scrollIntoViewIfNeeded();
  await expect(detailLink).toBeVisible();

  const before = await target.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { top: rect.top, bottom: rect.bottom, viewport: window.innerHeight, scrollY: window.scrollY };
  });
  expect(before.bottom).toBeGreaterThan(0);
  expect(before.top).toBeLessThan(before.viewport);

  await detailLink.click();
  await expect(page).toHaveURL(/\/papers\/\d+/);
  await expect(page.getByRole('link', { name: /返回原检索页与页码/ })).toBeVisible();
  await page.getByRole('link', { name: /返回原检索页与页码/ }).click();

  const restored = page.locator(`[data-search-paper="${targetId}"]`);
  await expect(restored).toBeVisible();
  await expect.poll(async () => restored.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return rect.bottom > 0 && rect.top < window.innerHeight;
  })).toBe(true);

  const after = await restored.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { top: rect.top, bottom: rect.bottom, viewport: window.innerHeight, scrollY: window.scrollY };
  });
  expect(after.bottom).toBeGreaterThan(0);
  expect(after.top).toBeLessThan(after.viewport);
  expect(searchPosts).toBe(1);
  page.off('request', onRequest);
});
