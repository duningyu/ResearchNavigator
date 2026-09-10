import { expect, test } from '@playwright/test';

const apiURL = process.env.RN_E2E_API_URL ?? 'http://127.0.0.1:18004';
const webURL = process.env.RN_E2E_BASE_URL ?? 'http://127.0.0.1:5174';
const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
const password = 'ux003-refresh-test-pass-123';

async function api(path: string, options: RequestInit = {}) {
  const response = await fetch(`${apiURL}${path}`, {
    ...options,
    headers: { 'content-type': 'application/json', ...(options.headers ?? {}) },
  });
  const text = await response.text();
  return { response, body: text ? JSON.parse(text) : null };
}

test('UX-003-A2 offers an explicit action that refreshes an expired search state', async ({ page }) => {
  const registered = await api('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({
      email: `ux003-refresh-${suffix}@example.test`,
      password,
      display_name: 'UX-003 refresh test',
    }),
  });
  expect(registered.response.ok).toBeTruthy();
  const token = registered.body.access_token as string;
  const user = registered.body.user as { id: number };
  const auth = { Authorization: `Bearer ${token}` };
  const projectResponse = await api('/api/projects', {
    method: 'POST',
    headers: auth,
    body: JSON.stringify({ name: `UX-003 ${suffix}`, description: 'test_only=true', broad_direction: 'test-only' }),
  });
  expect(projectResponse.response.ok).toBeTruthy();
  const project = projectResponse.body as { id: number };
  const searchResponse = await api('/api/search/papers', {
    method: 'POST',
    headers: auth,
    body: JSON.stringify({ query: 'expired-workspace', sources: ['fixture'], project_id: project.id, limit: 10, mode: 'auto', adapt_query: false }),
  });
  expect(searchResponse.response.ok).toBeTruthy();
  const search = searchResponse.body as { session_id: number; papers: Array<{ id: number }> };

  await page.goto(`${webURL}/?rn_backend=${encodeURIComponent(apiURL)}`);
  await page.evaluate(({ token: accessToken, user: account, apiOrigin }) => {
    localStorage.setItem('rn_access_token', accessToken);
    localStorage.setItem('rn_user', JSON.stringify(account));
    sessionStorage.setItem('rn_backend_origin', apiOrigin);
  }, { token, user, apiOrigin: apiURL });
  // Reopen the normal search route without a session query parameter. The
  // product must still expose the stale-state action from the saved workspace.
  await page.goto(`${webURL}/search?project=${project.id}&rn_backend=${encodeURIComponent(apiURL)}`);
  await page.getByPlaceholder(/关键词、题目、DOI/).waitFor();
  const tabIdentity = await page.evaluate(() => sessionStorage.getItem('rn-search-tab-v1'));
  const state = {
    query: 'expired-workspace',
    filters: { sources: ['fixture'], limit: 10, mode: 'auto', adapt_query: false },
    sessionId: search.session_id,
    resultIds: search.papers.map((paper) => paper.id),
    selectedIds: search.papers.slice(0, 1).map((paper) => paper.id),
    page: 1,
    scrollY: 100,
    anchor: { paperId: search.papers[0].id, offset: 10 },
  };
  await page.evaluate(({ state: workspace, accountId, tab, apiOrigin }) => {
    const key = JSON.stringify([accountId, `${apiOrigin}/api`, Number(new URL(location.href).searchParams.get('project')), tab]);
    sessionStorage.setItem('rn-search-workspace-v4', JSON.stringify([{
      key,
      queryIdentity: JSON.stringify([workspace.query, workspace.filters]),
      state: workspace,
      savedAt: Date.now() - 25 * 60 * 60 * 1000,
    }]));
  }, { state, accountId: user.id, tab: tabIdentity, apiOrigin: apiURL });

  await page.reload();
  await expect(page.getByText('检索现场已过期')).toBeVisible();
  const action = page.getByRole('button', { name: '重新确认并搜索' });
  await expect(action).toBeVisible();
  await action.click();
  await expect(page.getByText('检索现场已过期')).toHaveCount(0);
  await expect(page.getByText(/结果 · 第 1 页/)).toBeVisible();
});
