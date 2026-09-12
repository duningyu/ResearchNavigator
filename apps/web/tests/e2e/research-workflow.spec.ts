import { expect, test, type Page } from '@playwright/test';

async function register(page: Page, email: string, name: string) {
  await page.goto('/');
  await page.getByText('注册').click();
  await page.getByLabel('姓名').fill(name);
  await page.getByLabel('邮箱').fill(email);
  await page.getByLabel('密码').fill('e2e-research-pass-123');
  await page.getByRole('button', { name: '创建账户' }).click();
  await expect(page.getByRole('heading', { name: '今日研究起点' })).toBeVisible();
}

async function pickOptionByKeyboard(page: Page, name: string) {
  const active = page.locator('.ant-select-item-option-active').first();
  await active.waitFor({ state: 'attached', timeout: 15000 });
  for (let i = 0; i < 50; i += 1) {
    const text = await active.textContent().catch(() => null);
    if (text && text.includes(name)) break;
    await page.keyboard.press('ArrowDown');
    await page.waitForTimeout(60);
  }
  await page.keyboard.press('Enter');
}

async function chooseProject(page: Page, name: string) {
  const combo = page.locator('.ant-select', { hasText: '选择自己的研究方向' }).first();
  await combo.locator('input').first().focus();
  await page.keyboard.press('Enter');
  await pickOptionByKeyboard(page, name);
}

test('golden browser loop: explicit search corpus, analysis, favourites, compare, gap, challenge and human gate', async ({ page }) => {
  const suffix = Date.now();
  const email = `golden-${suffix}@example.com`;
  const projectName = `Golden project ${suffix}`;
  await register(page, email, 'Golden User');

  await page.getByRole('link', { name: '完善档案' }).click();
  await page.getByLabel('专业').fill('工业时序异常检测');
  await page.getByLabel('宽泛研究方向').fill('未来窗口预警与异常排序');
  await page.getByLabel('关键词').fill('anomaly detection');
  await page.getByLabel('关键词').press('Enter');
  await page.getByRole('button', { name: '保存档案' }).click();

  await page.goto('/projects');
  await page.getByRole('button', { name: '新建研究项目' }).click();
  await page.getByLabel('项目名称').fill(projectName);
  await page.getByLabel('研究方向').fill('未来窗口异常风险排序');
  await page.getByRole('button', { name: /^创\s*建$/ }).click();
  await expect(page.getByText(projectName)).toBeVisible();

  await page.getByRole('menuitem', { name: /找论文$/ }).click();
  await page.getByPlaceholder(/关键词、题目、DOI/).fill('anomaly detection');
  // The current product defaults to 50 results and exposes the option as “最多 50 篇”.
  // No selection is needed for this journey; keep the assertion focused on the actual search flow.
  await page.locator('#sources').click();
  await pickOptionByKeyboard(page, 'fixture');
  await page.getByRole('button', { name: /^搜\s*索$/ }).click();
  // Internal search fields are intentionally not exposed in the user UI.
  // Assert the current source-status contract instead of the retired debug text.
  await expect(page.getByText(/本地示例（非真实检索）.*已响应/)).toBeVisible();
  await expect(page.getByText('检索状态不代表全文可获取；全文情况请查看论文材料。')).toBeVisible();

  const resultLinks = page.getByRole('link', { name: '查看论文与证据' });
  await expect(resultLinks.first()).toBeVisible();
  const firstTitle = await resultLinks.first().locator('xpath=ancestor::li').locator('strong').first().innerText();
  const secondTitle = await resultLinks.nth(1).locator('xpath=ancestor::li').locator('strong').first().innerText();

  await resultLinks.first().click();
  await page.getByRole('button', { name: '收藏论文' }).click();
  await page.getByLabel('研究笔记').fill(`Golden note ${suffix}`);
  await page.getByRole('button', { name: '保存笔记' }).click();
  const paperProjectSelect = page.locator('.ant-select', { hasText: '选择研究课题，用于方向关联分析' }).first();
  await paperProjectSelect.locator('input').first().focus();
  await page.keyboard.press('Enter');
  await pickOptionByKeyboard(page, projectName);
  await page.getByRole('button', { name: '执行证据级分析' }).click();
  await expect(page.getByText('执行证据级分析 · 详细解释')).toBeVisible();
  await expect(page.getByText('方法创新')).toBeVisible();
  await expect(page.getByText('理论创新 / 理论贡献')).toBeVisible();
  await expect(page.getByText(/摘要级证据不足|证据等级/).first()).toBeVisible();
  await page.getByRole('link', { name: /返回原检索页与页码/ }).click();
  // The detail route renders the title in several evidence/summary sections;
  // the return assertion only needs to prove the restored result is visible.
  await expect(page.getByText(firstTitle).first()).toBeVisible();

  await page.getByText(secondTitle).locator('xpath=ancestor::li').getByRole('link', { name: '查看论文与证据' }).click();
  await page.getByRole('button', { name: '收藏论文' }).click();
  await page.getByRole('link', { name: /返回原检索页与页码/ }).click();

  await page.goto('/library');
  const firstLibraryRow = page.locator('li.library-paper-row').filter({ hasText: firstTitle });
  const secondLibraryRow = page.locator('li.library-paper-row').filter({ hasText: secondTitle });
  await expect(firstLibraryRow.getByRole('checkbox')).toBeVisible();
  await expect(secondLibraryRow.getByRole('checkbox')).toBeVisible();
  await firstLibraryRow.getByRole('checkbox').check();
  await secondLibraryRow.getByRole('checkbox').check();
  await expect(firstLibraryRow.getByRole('checkbox')).toBeChecked();
  await expect(secondLibraryRow.getByRole('checkbox')).toBeChecked();
  await expect(page.getByRole('button', { name: '对比选中论文' })).toBeEnabled();
  await page.getByRole('button', { name: '对比选中论文' }).click();
  await chooseProject(page, projectName);
  const comparisonResponse = page.waitForResponse((response) => response.url().includes('/comparisons') && response.request().method() === 'POST');
  await page.getByRole('button', { name: '生成证据级对比矩阵' }).click();
  await expect((await comparisonResponse).status()).toBe(201);
  await expect(page.getByText('先看结论')).toBeVisible();
  await expect(page.getByText(/已对照所选 2 篇论文/)).toBeVisible();
  await page.getByText('展开逐项核对依据').click();
  const evidenceDetails = page.locator('details[open]');
  await expect(evidenceDetails).toBeVisible();
  await expect(evidenceDetails.locator('.ant-table')).toBeVisible();
  await expect(evidenceDetails.getByText(/材料不足的字段不会用推测补齐/)).toBeVisible();

  await page.goto('/library');
  const firstGapRow = page.locator('li.library-paper-row').filter({ hasText: firstTitle });
  const secondGapRow = page.locator('li.library-paper-row').filter({ hasText: secondTitle });
  await firstGapRow.getByRole('checkbox').check();
  await secondGapRow.getByRole('checkbox').check();
  await expect(firstGapRow.getByRole('checkbox')).toBeChecked();
  await expect(secondGapRow.getByRole('checkbox')).toBeChecked();
  await expect(page.getByRole('button', { name: '探索候选研究空白' })).toBeEnabled();
  await page.getByRole('button', { name: '探索候选研究空白' }).click();
  await chooseProject(page, projectName);
  const gapResponse = page.waitForResponse((response) => response.url().endsWith('/gaps/generate') && response.request().method() === 'POST');
  await page.getByRole('button', { name: '构建证据矩阵并解释候选空白' }).click();
  await expect((await gapResponse).status()).toBe(409);
  await expect(page.getByTestId('scientific-decision')).toBeVisible();
  await expect(page.getByText('当前证据不足，暂不生成候选研究空白')).toBeVisible();
  await expect(page.getByText('当前证据还不足以确认一个可靠的研究空白。')).toBeVisible();
  await expect(page.getByText('未创建候选研究空白')).toBeVisible();
  await expect(page.locator('body')).not.toContainText('INSUFFICIENT_RELEVANT_CITED_EVIDENCE');
  await expect(page.getByRole('button', { name: '我已人工审阅并确认' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '创建研究计划' })).toHaveCount(0);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '打开导航菜单' }).click();
  await expect(page.getByText('找论文').last()).toBeVisible();
  await expect(page.getByText('比较与找空白').last()).toBeVisible();
  await expect(page.getByText('下一步计划').last()).toBeVisible();

  await page.goto('/papers/999999');
  await expect(page.getByText('论文载入失败')).toBeVisible();
});

test('user B cannot observe user A private project or library data', async ({ page }) => {
  const suffix = Date.now();
  await register(page, `owner-${suffix}@example.com`, 'Owner A');
  await page.goto('/projects');
  await page.getByRole('button', { name: '新建研究项目' }).click();
  await page.getByLabel('项目名称').fill(`A private project ${suffix}`);
  await page.getByRole('button', { name: /^创\s*建$/ }).click();
  await page.getByRole('button', { name: /退\s*出$/ }).click();

  // Reuse the normal registration/login helper so the second account follows
  // the current AuthPage contract rather than relying on the retired inline flow.
  await register(page, `other-${suffix}@example.com`, 'User B');
  await page.goto('/projects');
  await expect(page.getByText(`A private project ${suffix}`)).toHaveCount(0);
  await page.goto('/library');
  await expect(page.getByText('尚未收藏论文')).toBeVisible();
});
