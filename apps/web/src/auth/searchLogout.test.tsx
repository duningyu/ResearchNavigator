import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { AuthProvider, useAuth } from './AuthContext';
import { searchWorkspace } from '../lib/searchWorkspace';

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); searchWorkspace.clear(); });
it('另一标签页退出后立即撤销当前身份和迟到搜索结果', () => {
  localStorage.setItem('rn_access_token', 'local-test-only');
  localStorage.setItem('rn_user', JSON.stringify({ id: 1, email: 'test@example.invalid', display_name: 'test', is_admin: false }));
  const generation = searchWorkspace.beginRequest();
  const { result, unmount } = renderHook(() => useAuth(), { wrapper: AuthProvider });
  act(() => {
    localStorage.removeItem('rn_access_token');
    window.dispatchEvent(new StorageEvent('storage', { key: 'rn_access_token', newValue: null }));
  });
  expect(result.current.user).toBeNull();
  expect(result.current.token).toBeNull();
  expect(searchWorkspace.isCurrent(generation)).toBe(false);
  unmount();
});
it('退出在注销请求完成之前清除搜索现场，使迟到请求立即失效', async () => {
  localStorage.setItem('rn_access_token', 'local-test-only');
  localStorage.setItem('rn_user', JSON.stringify({ id: 1, email: 'test@example.invalid', display_name: 'test', is_admin: false }));
  let finish!: (response: Response) => void;
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
  const scope = { account: 1, environment: '/api', project: null, tab: 'test' };
  searchWorkspace.save(scope, { query: 'test', filters: {}, sessionId: 1, resultIds: [1], selectedIds: [1], page: 1, scrollY: 0 });
  const generation = searchWorkspace.beginRequest();
  const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
  let completion!: Promise<void>;
  act(() => { completion = result.current.clearSession(); });
  expect(searchWorkspace.load(scope)).toBeNull();
  expect(searchWorkspace.isCurrent(generation)).toBe(false);
  expect(result.current.user).toBeNull();
  await act(async () => { finish(new Response(null, { status: 204 })); await completion; });
});
