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

  await page.getByRole('menuitem', { name: /研究档案$/ }).click();
  await page.getByLabel('专业').fill('工业时序异常检测');
  await page.getByLabel('宽泛研究方向').fill('未来窗口预警与异常排序');
  await page.getByLabel('关键词').fill('anomaly detection');
  await page.getByLabel('关键词').press('Enter');
  await page.getByRole('button', { name: '保存档案' }).click();

  await page.getByRole('menuitem', { name: /研究项目$/ }).click();
  await page.getByRole('button', { name: '新建研究项目' }).click();
  await page.getByLabel('项目名称').fill(projectName);
  await page.getByLabel('研究方向').fill('未来窗口异常风险排序');
  await page.getByRole('button', { name: /^创\s*建$/ }).click();
  await expect(page.getByText(projectName)).toBeVisible();

  await page.getByRole('menuitem', { name: /论文搜索$/ }).click();
  await page.getByPlaceholder(/关键词、题目、DOI/).fill('anomaly detection');
  await page.getByText('Top 50').click();
  await page.locator('#sources').click();
  await pickOptionByKeyboard(page, 'fixture');
  await page.getByRole('button', { name: /^搜\s*索$/ }).click();
  await expect(page.getByText(/mode=discovery/)).toBeVisible();
  await expect(page.getByText(/shortfall=/)).toBeVisible();

  const resultLinks = page.getByRole('link', { name: '证据级分析' });
  await expect(resultLinks.first()).toBeVisible();
  const firstTitle = await resultLinks.first().locator('xpath=ancestor::li').locator('strong').first().innerText();
  const secondTitle = await resultLinks.nth(1).locator('xpath=ancestor::li').locator('strong').first().innerText();

  await resultLinks.first().click();
  await page.getByRole('button', { name: '收藏论文' }).click();
  await page.getByLabel('研究笔记').fill(`Golden note ${suffix}`);
  await page.getByRole('button', { name: '保存笔记' }).click();
  const paperProjectSelect = page.locator('.ant-select', { hasText: '选择研究项目，用于方向关联分析' }).first();
  await paperProjectSelect.locator('input').first().focus();
  await page.keyboard.press('Enter');
  await pickOptionByKeyboard(page, projectName);
  await page.getByRole('button', { name: '执行证据级分析' }).click();
  await expect(page.getByText('执行证据级分析 · 详细解释')).toBeVisible();
  await expect(page.getByText('方法创新')).toBeVisible();
  await expect(page.getByText('理论创新 / 理论贡献')).toBeVisible();
  await expect(page.getByText(/摘要级证据不足|证据等级/).first()).toBeVisible();
  await page.getByRole('link', { name: /返回原检索页与页码/ }).click();
  await expect(page.getByText(firstTitle)).toBeVisible();

  await page.getByText(secondTitle).locator('xpath=ancestor::li').getByRole('link', { name: '证据级分析' }).click();
  await page.getByRole('button', { name: '收藏论文' }).click();
  await page.getByRole('link', { name: /返回原检索页与页码/ }).click();

  await page.getByRole('menuitem', { name: /我的论文库$/ }).click();
  await page.getByText(firstTitle).locator('xpath=ancestor::li').getByRole('checkbox').click({ force: true });
  await page.getByText(secondTitle).locator('xpath=ancestor::li').getByRole('checkbox').click({ force: true });
  await page.getByRole('button', { name: '对比选中论文' }).click();
  await chooseProject(page, projectName);
  await page.getByRole('button', { name: '生成证据级对比矩阵' }).click();
  await expect(page.getByText(/证据级对比矩阵 #/).first()).toBeVisible();
  await expect(page.getByText('研究问题与任务定义')).toBeVisible();
  await expect(page.getByText('与当前研究方向关联度')).toBeVisible();

  await page.getByRole('menuitem', { name: /我的论文库$/ }).click();
  await page.getByText(firstTitle).locator('xpath=ancestor::li').getByRole('checkbox').click({ force: true });
  await page.getByText(secondTitle).locator('xpath=ancestor::li').getByRole('checkbox').click({ force: true });
  await page.getByRole('button', { name: '探索候选研究空白' }).click();
  await chooseProject(page, projectName);
  await page.getByRole('button', { name: '构建证据矩阵并解释候选空白' }).click();
  await expect(page.getByText(/Gap Explanation Agent/).first()).toBeVisible();
  await expect(page.getByText('系统推断（非论文直接陈述）').first()).toBeVisible();
  const challengeButton = page.getByRole('button', { name: '执行 Challenge Search' }).first();
  const challengeResponse = page.waitForResponse((response) => response.url().includes('/api/gaps/') && response.url().endsWith('/challenge') && response.request().method() === 'POST');
  await challengeButton.click();
  await expect((await challengeResponse).status()).toBe(200);
  await expect(page.getByText('awaiting_human_confirmation').first()).toBeVisible();
  const confirmResponse = page.waitForResponse((response) => response.url().includes('/api/gaps/') && response.url().endsWith('/confirm') && response.request().method() === 'POST');
  await page.getByRole('button', { name: '我已人工审阅并确认' }).first().click();
  await expect((await confirmResponse).status()).toBe(200);
  const planResponse = page.waitForResponse((response) => response.url().endsWith('/api/plans') && response.request().method() === 'POST');
  await page.getByRole('button', { name: '创建研究计划' }).first().click();
  await expect((await planResponse).status()).toBe(201);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '打开导航菜单' }).click();
  await expect(page.getByText('论文搜索').last()).toBeVisible();
  await expect(page.getByText('论文对比').last()).toBeVisible();
  await expect(page.getByText('候选研究空白').last()).toBeVisible();

  await page.goto('/papers/999999');
  await expect(page.getByText('论文载入失败')).toBeVisible();
});

test('user B cannot observe user A private project or library data', async ({ page }) => {
  const suffix = Date.now();
  await register(page, `owner-${suffix}@example.com`, 'Owner A');
  await page.getByRole('menuitem', { name: /研究项目$/ }).click();
  await page.getByRole('button', { name: '新建研究项目' }).click();
  await page.getByLabel('项目名称').fill(`A private project ${suffix}`);
  await page.getByRole('button', { name: /^创\s*建$/ }).click();
  await page.getByRole('button', { name: /退\s*出$/ }).click();

  await page.getByText('注册').click();
  await page.getByLabel('姓名').fill('User B');
  await page.getByLabel('邮箱').fill(`other-${suffix}@example.com`);
  await page.getByLabel('密码').fill('e2e-research-pass-123');
  await page.getByRole('button', { name: '创建账户' }).click();
  await page.getByRole('menuitem', { name: /研究项目$/ }).click();
  await expect(page.getByText(`A private project ${suffix}`)).toHaveCount(0);
  await page.getByRole('menuitem', { name: /我的论文库$/ }).click();
  await expect(page.getByText('尚未收藏论文')).toBeVisible();
});
