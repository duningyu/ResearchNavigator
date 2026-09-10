import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { AuthProvider } from '../auth/AuthContext';
import { AppShell } from '../components/AppShell';
import { AuthPage } from '../pages/AuthPage';
import { DashboardPage } from '../pages/DashboardPage';

beforeEach(() => localStorage.clear());
afterEach(() => { cleanup(); localStorage.clear(); });

describe('research workspace experience', () => {
  it('returns from comparison to the same project search scope without leaking comparison parameters', async () => {
    function Destination() { const location = useLocation(); return <output>{location.pathname + location.search}</output>; }
    render(<MemoryRouter initialEntries={['/compare?project=7&paperSet=8&comparison=9']}><AuthProvider><Routes><Route element={<AppShell />}><Route path="*" element={<Destination />} /></Route></Routes></AuthProvider></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: '打开导航菜单' }));
    fireEvent.click(screen.getByRole('menuitem', { name: /找论文/ }));
    expect(await screen.findByText('/search?project=7')).toBeInTheDocument();
  });
  it('explains the evidence-driven workflow before a researcher signs in', () => {
    render(<MemoryRouter><AuthProvider><AuthPage /></AuthProvider></MemoryRouter>);
    expect(screen.getByText('RESEARCH NAVIGATOR · 2.1')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /把证据变成\s*下一步研究决策/ })).toBeInTheDocument();
    expect(screen.getByText('从研究档案到可执行计划，始终保留来源、边界和人工确认。')).toBeInTheDocument();
  });

  it('offers an immediate search action from the signed-in workspace', () => {
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    expect(screen.getByRole('heading', { name: '今日研究起点' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /开始检索/ })).toHaveAttribute('href', '/search');
    expect(screen.queryByText('SQLite')).not.toBeInTheDocument();
    expect(screen.queryByText('本地运行')).not.toBeInTheDocument();
    expect(screen.getByText('以当前连接的服务为准')).toBeInTheDocument();
  });

  it('keeps every workflow destination reachable through a drawer on a narrow viewport', () => {
    localStorage.setItem('rn_access_token', 'token');
    localStorage.setItem('rn_user', JSON.stringify({ id: 1, email: 'admin@example.test', display_name: 'Researcher', is_admin: true }));
    render(<MemoryRouter initialEntries={['/search']}><AuthProvider><Routes><Route element={<AppShell />}><Route path="search" element={<div>search body</div>} /></Route></Routes></AuthProvider></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '打开导航菜单' }));
    for (const label of ['研究首页', '找论文', '我的论文', '比较与找空白', '下一步计划']) {
      expect(screen.getByRole('menuitem', { name: new RegExp(label) })).toBeInTheDocument();
    }
    for (const label of ['任务进度', '方向聚类', '专家评测']) {
      expect(screen.queryByRole('menuitem', { name: new RegExp(label) })).not.toBeInTheDocument();
    }
    expect(screen.getByText('备份与恢复')).toBeInTheDocument();
    expect(screen.getByText('管理员配置')).toBeInTheDocument();
  });

  it('moves focus to the new page heading after a top-level navigation', async () => {
    localStorage.setItem('rn_access_token', 'token');
    localStorage.setItem('rn_user', JSON.stringify({ id: 1, email: 'admin@example.test', display_name: 'Researcher' }));
    render(<MemoryRouter initialEntries={['/search']}><AuthProvider><Routes><Route element={<AppShell />}><Route path="search" element={<div><h1>论文检索</h1></div>} /><Route path="library" element={<div><h1>我的论文库</h1></div>} /></Route></Routes></AuthProvider></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '打开导航菜单' }));
    fireEvent.click(screen.getByRole('menuitem', { name: /我的论文/ }));
    await screen.findByRole('heading', { name: '我的论文库', level: 1 });
    await waitFor(() => expect(document.activeElement).toBe(document.querySelector('main.app-content')));
  });

  it('returns focus to the restored search result after leaving its detail route', async () => {
    localStorage.setItem('rn_access_token', 'token');
    localStorage.setItem('rn_user', JSON.stringify({ id: 1, email: 'admin@example.test', display_name: 'Researcher' }));
    function SearchFixture() { return <div><h1>论文检索</h1><button data-search-paper="42">目标论文</button><a href="/papers/42">查看详情</a></div>; }
    function DetailFixture() { const navigate = useNavigate(); return <div><h1>论文详情</h1><button onClick={() => navigate('/search')}>返回搜索</button></div>; }
    render(<MemoryRouter initialEntries={['/search', '/papers/42']} initialIndex={1}><AuthProvider><Routes><Route element={<AppShell />}><Route path="search" element={<SearchFixture />} /><Route path="papers/:id" element={<DetailFixture />} /></Route></Routes></AuthProvider></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '返回搜索' }));
    const result = await screen.findByRole('button', { name: '目标论文' });
    await waitFor(() => expect(document.activeElement).toBe(result));
  });
});
