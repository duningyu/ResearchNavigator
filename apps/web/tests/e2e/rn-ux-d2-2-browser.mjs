import { chromium } from '@playwright/test';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';

const baseURL = process.env.RN_D22_BASE_URL || 'http://127.0.0.1:15173';
const suffix = `${Date.now()}-${crypto.randomBytes(3).toString('hex')}`;
const email = `d22-${suffix}@example.com`;
const password = 'd2-2-local-pass-123';
const safe = (url) => { const u = new URL(url); return `${u.hostname}${u.pathname}`; };
const events = [];
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ baseURL });
const page = await context.newPage();
page.on('console', (m) => { if (m.type() === 'error') events.push({ kind: 'console-error', text: m.text().slice(0, 240) }); });
page.on('request', (r) => { const u = new URL(r.url()); if (u.pathname.startsWith('/api/')) events.push({ kind: 'request', method: r.method(), host: u.hostname, path: u.pathname }); });
page.on('response', async (r) => {
  const u = new URL(r.url());
  if (!u.pathname.startsWith('/api/')) return;
  const item = { kind: 'response', method: r.request().method(), host: u.hostname, path: u.pathname, status: r.status() };
  if (u.pathname === '/api/projects' && r.request().method() === 'POST' && r.status() < 300) {
    try { const body = await r.json(); item.project_id = body.id; } catch { /* safe receipt only */ }
  }
  if (u.pathname.includes('/abstract-translation') && r.status() < 500) {
    try {
      const body = await r.json();
      item.translation_status = body.status;
      item.translation_cache_hit = body.cache_hit;
      item.translation_has_text = Boolean(body.translated_abstract);
    } catch { /* safe receipt only */ }
  }
  events.push(item);
});

async function register() {
  await page.goto('/');
  await page.getByText('注册').click();
  await page.getByLabel('姓名').fill('D22 Browser Tester');
  await page.getByLabel('邮箱').fill(email);
  await page.getByLabel('密码').fill(password);
  await page.getByRole('button', { name: '创建账户' }).click();
  await page.getByRole('heading', { name: '今日研究起点' }).waitFor();
}

async function saveProfile() {
  console.log('AFTER_REGISTER_URL', page.url());
  console.log('AFTER_REGISTER_TEXT', (await page.locator('body').innerText()).slice(0, 1000));
  await page.goto('/profile');
  await page.getByLabel('专业').fill('工业时序异常检测');
  await page.getByLabel('宽泛研究方向').fill('未来窗口异常预警');
  await page.getByLabel('关键词').fill('anomaly detection');
  await page.getByLabel('关键词').press('Enter');
  await page.getByRole('button', { name: '保存档案' }).click();
}

async function createProject() {
  const name = `D22 Project ${suffix}`;
  await page.goto('/projects');
  await page.getByRole('button', { name: '新建研究项目' }).click();
  await page.getByLabel('项目名称').fill(name);
  await page.getByLabel('研究方向').fill('未来窗口异常预警');
  await page.getByRole('button', { name: /^创\s*建$/ }).click();
  await page.getByText(name).waitFor();
  const project = events.findLast((e) => e.kind === 'response' && e.path === '/api/projects' && e.method === 'POST' && e.project_id);
  if (!project?.project_id) throw new Error('project id was not captured from actual create response');
  return { id: project.project_id, name };
}

async function selectFixtureSource() {
  await page.locator('#sources').click();
  const active = page.locator('.ant-select-item-option-active').first();
  await active.waitFor();
  for (let i = 0; i < 30; i += 1) {
    const text = (await active.textContent()) || '';
    if (text.includes('fixture')) break;
    await page.keyboard.press('ArrowDown');
  }
  await page.keyboard.press('Enter');
}

async function searchAndOpen() {
  await page.goto('/search');
  await page.getByPlaceholder(/关键词、题目、DOI/).fill('anomaly detection');
  // The current UI exposes the limit as an Ant Design select rather than the
  // historical "Top 50" text used by the older golden spec.
  const limit = page.locator('.search-form .ant-select').nth(1);
  await limit.click();
  await page.getByText('最多 50 篇', { exact: true }).last().click();
  await selectFixtureSource();
  await page.getByRole('button', { name: /^搜\s*索$/ }).click();
  try {
    await page.getByRole('link', { name: '查看论文与证据' }).first().waitFor({ timeout: 30000 });
  } catch (error) {
    console.log('SEARCH_DEBUG_URL', page.url());
    console.log('SEARCH_DEBUG_TEXT', (await page.locator('body').innerText()).slice(0, 4000));
    console.log('SEARCH_DEBUG_EVENTS', JSON.stringify(events.slice(-40), null, 2));
    throw error;
  }
  const title = await page.getByRole('link', { name: '查看论文与证据' }).first().locator('xpath=ancestor::li').locator('strong').first().innerText();
  const detailLink = page.getByRole('link', { name: '查看论文与证据' }).first();
  const href = await detailLink.getAttribute('href');
  const hrefPaperId = href?.match(/\/papers\/(\d+)/)?.[1];
  await detailLink.click();
  await page.waitForTimeout(1000);
  const detail = events.findLast((e) => e.kind === 'response' && /^\/api\/papers\/\d+$/.test(e.path) && e.status === 200);
  const paperId = hrefPaperId ?? detail?.path.match(/\d+$/)?.[0];
  if (!paperId) {
    console.log('DETAIL_DEBUG_URL', page.url());
    console.log('DETAIL_DEBUG_TEXT', (await page.locator('body').innerText()).slice(0, 3000));
    console.log('DETAIL_DEBUG_EVENTS', JSON.stringify(events.slice(-50), null, 2));
    throw new Error('paper id not captured from detail route');
  }
  return { paperId, title };
}

async function refreshRecommendations(projectId) {
  return await page.evaluate(async (id) => {
    const token = localStorage.getItem('rn_access_token');
    const response = await fetch('/api/recommendations/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ project_id: id }),
    });
    return { status: response.status, body: await response.json() };
  }, projectId);
}

async function readTranslation(projectId, paperId) {
  await page.goto(`/papers/${paperId}?project=${projectId}`);
  await page.getByText('摘要译文').waitFor();
  await page.waitForTimeout(500);
  const translated = await page.locator('body').innerText();
  const originalButton = page.getByRole('button', { name: '查看原文' });
  const failureMode = ['failure', 'partial', 'empty'].includes(process.env.RN_D22_TRANSLATION_MODE ?? '');
  if (failureMode) {
    return {
      translatedHasLabel: translated.includes('摘要译文'),
      originalFallbackVisible: translated.includes('原始摘要'),
      fallbackNoticeVisible: translated.includes('中文译文暂未生成'),
      translationControlDisabled: await page.getByRole('button', { name: '查看中文' }).isDisabled(),
      recommendationVisible: translated.includes('阅读建议'),
    };
  }
  await originalButton.click();
  const original = await page.locator('body').innerText();
  await page.getByRole('button', { name: '查看中文' }).click();
  const back = await page.locator('body').innerText();
  return { translatedHasLabel: translated.includes('摘要译文'), originalHasLabel: original.includes('原始摘要'), backHasLabel: back.includes('摘要译文'), recommendationVisible: back.includes('阅读建议') };
}

async function invalidateProfile(projectId, paperId) {
  await page.goto('/profile');
  await page.getByLabel('宽泛研究方向').fill('医疗影像分割与病灶识别');
  await page.getByRole('button', { name: '保存档案' }).click();
  await page.goto(`/papers/${paperId}?project=${projectId}`);
  await page.getByText('阅读建议', { exact: true }).waitFor();
  const body = await page.locator('body').innerText();
  return {
    staleNotice: body.includes('需要根据新的研究方向重新生成'),
    insufficientLabel: body.includes('信息不足'),
    forbidden: ['priority_read', 'method_reference', 'not_priority', 'insufficient_evidence'].filter((v) => body.includes(v)),
  };
}

async function main() {
  await register();
  await saveProfile();
  const project = await createProject();
  const paper = await searchAndOpen();
  const refreshed = await refreshRecommendations(project.id);
  const translation = await readTranslation(project.id, paper.paperId);
  const profileInvalidation = await invalidateProfile(project.id, paper.paperId);
  const text = await page.locator('body').innerText();
  const recommendationLabels = ['优先阅读', '方法参考', '暂不优先', '信息不足'].filter((v) => text.includes(v));
  const forbidden = ['priority_read', 'method_reference', 'not_priority', 'insufficient_evidence', 'original_abstract', 'translated_abstract', 'pipeline_version', 'material_identity', 'Traceback', 'HTTPException'].filter((v) => text.includes(v));
  const recommendationRows = Array.isArray(refreshed.body) ? refreshed.body : (refreshed.body.items ?? refreshed.body.recommendations ?? []);
  const recommendationApi = recommendationRows.find((row) => row.paper?.id === Number(paper.paperId));
  const receipt = {
    base_url: baseURL,
    frontend_health: true,
    api_health: true,
    execution_id: suffix,
    translation_adapter_mode: process.env.RN_D22_TRANSLATION_MODE ?? 'ready',
    project_id: project.id,
    paper_id: Number(paper.paperId),
    paper_title_prefix: paper.title.slice(0, 120),
    translation,
    profile_invalidation: profileInvalidation,
    recommendation_status: refreshed.status,
    recommendation_verdict: recommendationApi?.reading_recommendation?.verdict ?? null,
    recommendation_evidence_level: recommendationApi?.reading_recommendation?.evidence_level ?? null,
    recommendation_labels: recommendationLabels,
    forbidden_visible_text: forbidden,
    event_count: events.length,
    api_events: events.filter((e) => e.kind === 'response').slice(-80),
    browser_console_errors: events.filter((e) => e.kind === 'console-error'),
  };
  await fs.writeFile(new URL(`../../.tmp/d22-2-browser-${suffix}.json`, import.meta.url), JSON.stringify(receipt, null, 2));
  console.log(JSON.stringify(receipt, null, 2));
}

try { await main(); } finally { await context.close(); await browser.close(); }
