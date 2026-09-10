import { beforeEach, describe, expect, it } from 'vitest';
import { SearchWorkspaceStore, resolveSearchTabIdentity, resolveSearchPosition, type SearchWorkspace } from './searchWorkspace';

const scope = { account: 1, environment: 'https://example.invalid/api', project: 2, tab: 'tab-a' };
const state: SearchWorkspace = {
  query: '图像分割', filters: { sources: ['arxiv'], limit: 20 },
  sessionId: 7, resultIds: [9, 3, 8], selectedIds: [3], page: 2, scrollY: 321,
};
describe('搜索现场的隔离、生命周期和迟到请求', () => {
  it('恢复来源编辑式和关闭自动适配的选择', () => {
    const store = new SearchWorkspaceStore(sessionStorage, () => 100);
    const edited = { ...state, filters: { ...state.filters, adapt_query: false, source_queries: { arxiv: 'ti:"segmentation"' } } };
    store.save(scope, edited);
    expect(new SearchWorkspaceStore(sessionStorage, () => 101).load(scope)).toEqual(edited);
  });
  it('保存可见论文锚点与偏移，缺失锚点回到有效页并说明原因', () => {
    const store = new SearchWorkspaceStore(sessionStorage, () => 100);
    const anchored = { ...state, anchor: { paperId: 3, offset: -20 } };
    store.save(scope, anchored);
    expect(store.load(scope)?.anchor).toEqual(anchored.anchor);
    expect(resolveSearchPosition(anchored, [9, 3, 8], 2)).toEqual({ page: 1, anchor: anchored.anchor, notice: null });
    expect(resolveSearchPosition(anchored, [9], 2)).toEqual({ page: 1, anchor: null, notice: '原定位论文已不可用，已返回可用结果页；请重新确认选文。' });
  });
  beforeEach(() => sessionStorage.clear());
  it('同标签页导航和刷新保留身份；没有现有标签身份时才创建新身份', () => {
    const first = resolveSearchTabIdentity(sessionStorage, 'navigate', () => 'first');
    expect(resolveSearchTabIdentity(sessionStorage, 'reload', () => 'reload')).toBe(first);
    expect(resolveSearchTabIdentity(sessionStorage, 'navigate', () => 'same-tab')).toBe(first);
    sessionStorage.clear();
    expect(resolveSearchTabIdentity(sessionStorage, 'navigate', () => 'new-tab')).toBe('new-tab');
  });
  it('恢复完整现场，而不只是关键词', () => {
    const store = new SearchWorkspaceStore(sessionStorage, () => 100);
    store.save(scope, state);
    expect(store.load(scope)).toEqual(state);
    for (const changed of [{ account: 2 }, { project: 3 }, { environment: 'other' }, { tab: 'b' }]) {
      expect(store.load({ ...scope, ...changed })).toBeNull();
    }
  });
  it('同一项目会话复用现场，项目、账号和环境变化严格隔离', () => {
    const store = new SearchWorkspaceStore(sessionStorage, () => 100);
    const projectA = { ...scope, project: 11 };
    const projectB = { ...scope, project: 12 };
    const accountB = { ...scope, account: 2 };
    const environmentB = { ...scope, environment: 'https://other.invalid/api' };
    const stateA = { ...state, sessionId: 11, selectedIds: [3] };
    const stateB = { ...state, sessionId: 12, selectedIds: [8] };

    store.save(projectA, stateA);
    store.save(projectB, stateB);

    const reloaded = new SearchWorkspaceStore(sessionStorage, () => 100);
    expect(reloaded.load(projectA, 11)).toEqual(stateA);
    expect(reloaded.load(projectB, 12)).toEqual(stateB);
    expect(reloaded.load(projectB, 11)).toBeNull();
    expect(reloaded.load(accountB, 11)).toBeNull();
    expect(reloaded.load(environmentB, 11)).toBeNull();
    expect(reloaded.load(projectA, 11)).toEqual(stateA);
  });
  it('过期和缓存版本不匹配不能恢复', () => {
    let now = 100;
    const store = new SearchWorkspaceStore(sessionStorage, () => now);
    store.save(scope, state);
    now += 24 * 60 * 60 * 1000;
    expect(store.load(scope)).toBeNull();
    sessionStorage.setItem('rn-search-workspace-v0', 'legacy');
    expect(store.load(scope)).toBeNull();
  });
  it('最多保留十份现场', () => {
    const store = new SearchWorkspaceStore(sessionStorage, () => 100);
    for (let i = 0; i < 11; i++) store.save({ ...scope, project: i }, state);
    expect(store.load({ ...scope, project: 0 })).toBeNull();
    expect(store.load({ ...scope, project: 10 })).toEqual(state);
  });
  it.each([
    { resultIds: [9, 'secret'] }, { selectedIds: [100] },
    { page: -1 }, { scrollY: -1 }, { sessionId: 0 },
    { filters: { sources: [null] } },
  ])('损坏的现场拒绝恢复并解释原因: %j', (damage) => {
    const store = new SearchWorkspaceStore(sessionStorage, () => 100);
    store.save(scope, state);
    const key = sessionStorage.key(0)!;
    const entries = JSON.parse(sessionStorage.getItem(key)!);
    Object.assign(entries[0].state, damage);
    sessionStorage.setItem(key, JSON.stringify(entries));
    const restored = new SearchWorkspaceStore(sessionStorage, () => 100);
    expect(restored.load(scope)).toBeNull();
    expect(restored.notice).toContain('损坏');
  });
  it('解释过期和存储禁用，而不是静默丢失现场', () => {
    let now = 100;
    const store = new SearchWorkspaceStore(sessionStorage, () => now);
    store.save(scope, state);
    now += 86400000;
    expect(store.load(scope)).toBeNull();
    expect(store.notice).toContain('过期');
    const disabled = new SearchWorkspaceStore();
    expect(disabled.notice).toContain('刷新');
  });
  it('同一范围的多个查询独立保存，返回指定会话不丢旧现场', () => {
    const store = new SearchWorkspaceStore(sessionStorage);
    store.save(scope, state);
    store.save(scope, { ...state, query: '检索增强生成', sessionId: 8, selectedIds: [] });
    expect(store.load(scope, 7)).toEqual(state);
    expect(store.load(scope, 8)?.query).toBe('检索增强生成');
    expect(store.load(scope, 99)).toBeNull();
    expect(store.load(scope)?.sessionId).toBe(8);
  });
  it('存储被禁用时保持内存现场，退出立即清空', () => {
    const broken = { getItem: () => { throw Error('disabled'); }, setItem: () => { throw Error('disabled'); }, removeItem: () => {} };
    const store = new SearchWorkspaceStore(broken);
    store.save(scope, state);
    expect(store.load(scope)).toEqual(state);
    const request = store.beginRequest();
    store.clear();
    expect(store.load(scope)).toBeNull();
    expect(store.isCurrent(request)).toBe(false);
  });
  it('新请求发出后旧响应不能覆盖，退出后响应也不能写入', () => {
    const store = new SearchWorkspaceStore(sessionStorage);
    const old = store.beginRequest();
    const current = store.beginRequest();
    expect(store.saveIfCurrent(old, scope, state)).toBe(false);
    expect(store.saveIfCurrent(current, scope, state)).toBe(true);
    store.clear();
    expect(store.saveIfCurrent(current, scope, state)).toBe(false);
    expect(store.load(scope)).toBeNull();
  });
});
