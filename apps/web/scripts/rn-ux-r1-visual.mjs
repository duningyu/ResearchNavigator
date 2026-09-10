// Offline UI smoke only. No production session, network or backend integration claim.
import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
const output = resolve(process.env.RN_UX_VISUAL_OUTPUT ?? '../../evidence/rn-ux-r1');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
let externalBlocked = 0;
await context.route('**/*', async (route) => {
  const url = new URL(route.request().url());
  if (url.origin !== 'http://127.0.0.1:5186') { externalBlocked++; return route.abort(); }
  if (url.pathname.startsWith('/api/')) return route.fulfill({ json: url.pathname.endsWith('/health') ? { status: 'ok', database: 'ok' } : [] });
  return route.continue();
});
await context.addInitScript(() => {
  localStorage.setItem('rn_access_token', 'OFFLINE-UI-DOUBLE-NOT-A-REAL-TOKEN');
  localStorage.setItem('rn_user', JSON.stringify({ id: 999, email: 'offline@example.invalid', display_name: '离线验收', is_admin: false }));
});
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(error.name));
try {
  await page.goto('http://127.0.0.1:5186/');
  await page.getByRole('heading', { name: '今日研究起点' }).waitFor();
  for (const label of ['研究首页', '找论文', '我的论文', '比较与找空白', '下一步计划']) await page.getByRole('menuitem').filter({ hasText: label }).waitFor();
  await page.screenshot({ path: resolve(output, 'desktop.png'), fullPage: true });
  const darkText = await page.locator('.dashboard-hero .ant-typography').last().evaluate((el) => getComputedStyle(el).color);
  if (darkText === 'rgb(0, 0, 0)' || darkText === 'rgba(0, 0, 0, 0.88)') throw new Error('DARK_SURFACE_TEXT_CONTRAST_REGRESSION');
  const contrast = await page.locator('.metric-card .ant-typography-secondary').first().evaluate((el) => {
    const components = getComputedStyle(el).color.match(/[\d.]+/g).map(Number);
    const alpha = components[3] ?? 1;
    const luminance = components.slice(0, 3).map((v) => (v * alpha + 255 * (1 - alpha)) / 255)
      .map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
      .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
    return 1.05 / (luminance + .05);
  });
  if (contrast < 4.5) throw new Error(`SECONDARY_TEXT_CONTRAST_${contrast.toFixed(2)}_BELOW_4_5`);
  // Reflow proxy: half the CSS viewport. This is NOT actual browser zoom proof.
  await page.setViewportSize({ width: 720, height: 500 });
  await page.screenshot({ path: resolve(output, 'reflow-720.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '打开导航菜单' }).waitFor();
  await page.screenshot({ path: resolve(output, 'narrow.png'), fullPage: true });
  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  await page.getByRole('button', { name: '打开导航菜单' }).click();
  await page.getByRole('menuitem').filter({ hasText: '找论文' }).click();
  await page.waitForURL('**/search');
  await page.getByRole('heading', { name: '今日研究起点' }).waitFor({ state: 'hidden' });
  await page.locator('.ant-drawer-open').waitFor({ state: 'hidden' });
  await page.getByRole('menuitem').filter({ hasText: '找论文' }).waitFor({ state: 'hidden' });
  await page.screenshot({ path: resolve(output, 'search-narrow.png'), fullPage: true });
  const papers = Array.from({ length: 50 }, (_, index) => ({
    id: index + 1, title: `Offline evidence paper ${index + 1}`, authors: [],
    keywords: [], source_urls: [], source_provenance: [], is_fixture: true,
    abstract: 'Synthetic browser fixture: this is not live scholarly source evidence.',
    abstract_evidence_verified: false,
  }));
  let unexpectedWrites = 0;
  await page.route(/^http:\/\/127\.0\.0\.1:5186\/api\//, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() !== 'GET') { unexpectedWrites++; return route.abort(); }
    if (path === '/api/search/sessions/7') return route.fulfill({ json: {
      id: 7, project_id: 7, query: 'semantic segmentation', filters: { sources: ['arxiv'], limit: 50 },
      source_status: {}, result_ids: papers.map((paper) => paper.id), result_count: 50,
      search_mode: 'precise', composition: {}, created_at: new Date().toISOString(),
    } });
    // Reverse response order deliberately; saved search ranking must prevail.
    if (path === '/api/search/sessions/7/papers') return route.fulfill({ json: [...papers].reverse() });
    if (path === '/api/papers/23') return route.fulfill({ json: papers[22] });
    if (path === '/api/papers/23/analysis') return route.fulfill({ status: 404, json: { detail: 'Not found' } });
    return route.fulfill({ json: path.endsWith('/health') ? { status: 'ok', database: 'ok' } : [] });
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('http://127.0.0.1:5186/search?session=7&page=3&project=7');
  await page.getByRole('checkbox', { name: '选择 Offline evidence paper 21', exact: true }).check();
  await page.getByRole('checkbox', { name: '选择 Offline evidence paper 23', exact: true }).check();
  const row = page.locator('.ant-list-item').filter({ has: page.getByRole('checkbox', { name: '选择 Offline evidence paper 23', exact: true }) });
  await row.scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(output, 'search-selected.png'), fullPage: true });
  await row.getByRole('link', { name: '查看论文与证据' }).click();
  await page.getByRole('link', { name: '← 返回原检索页与页码' }).click();
  const assertRestored = async () => {
    await page.getByRole('checkbox', { name: '选择 Offline evidence paper 21', exact: true }).waitFor();
    for (const id of [21, 23]) if (!await page.getByRole('checkbox', { name: `选择 Offline evidence paper ${id}`, exact: true }).isChecked()) throw new Error('SELECTION_NOT_RESTORED');
    if (await page.getByPlaceholder('关键词、题目、DOI、arXiv ID、作者或数据集').inputValue() !== 'semantic segmentation') throw new Error('QUERY_NOT_RESTORED');
    if (!page.url().includes('page=3')) throw new Error('PAGE_NOT_RESTORED');
    const first = await page.locator('.ant-list-item').first().innerText();
    if (!first.includes('Offline evidence paper 21')) throw new Error('RESULT_ORDER_NOT_RESTORED');
  };
  await assertRestored();
  await page.reload();
  await assertRestored();
  await page.getByRole('link', { name: '比较所选论文' }).click();
  await page.waitForURL('**/compare?**');
  await page.getByRole('menuitem').filter({ hasText: '找论文' }).click();
  await assertRestored();
  if (!new URL(page.url()).searchParams.get('project')) throw new Error('PROJECT_SCOPE_NOT_RESTORED');
  await page.screenshot({ path: resolve(output, 'search-restored.png'), fullPage: true });
  if (unexpectedWrites) throw new Error('RESTORE_CREATED_UNEXPECTED_JOB_OR_SEARCH');
  console.log(JSON.stringify({ scope: 'LOCAL_PROVIDER_DOUBLE_UI', screenshots: 6, searchRestore: 'PAGE_3_TWO_SELECTED_DETAIL_COMPARE_SIDEBAR_RELOAD_PASS', unexpectedWrites, secondaryTextContrast: contrast, actualBrowserZoom: 'NOT_EXECUTED', externalBlocked, pageErrors: errors, horizontalOverflow }));
  if (errors.length || horizontalOverflow) process.exitCode = 1;
} catch (error) {
  await page.screenshot({ path: resolve(output, 'failure-local-only.png'), fullPage: true });
  console.error(JSON.stringify({ stage: 'LOCAL_DOUBLE_UI', error: error.name, assertion: error.message, pageText: (await page.locator('body').innerText()).slice(0, 5000), pageErrors: errors }));
  process.exitCode = 1;
} finally { await browser.close(); }
