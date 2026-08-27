import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../auth/AuthContext';
import { AppShell } from '../components/AppShell';
import { AuthPage } from '../pages/AuthPage';
import { DashboardPage } from '../pages/DashboardPage';

beforeEach(() => localStorage.clear());
afterEach(() => { cleanup(); localStorage.clear(); });

describe('research workspace experience', () => {
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
  });

  it('keeps every workflow destination reachable through a drawer on a narrow viewport', () => {
    localStorage.setItem('rn_access_token', 'token');
    localStorage.setItem('rn_user', JSON.stringify({ id: 1, email: 'admin@example.test', display_name: 'Researcher', is_admin: true }));
    render(<MemoryRouter initialEntries={['/search']}><AuthProvider><Routes><Route element={<AppShell />}><Route path="search" element={<div>search body</div>} /></Route></Routes></AuthProvider></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '打开导航菜单' }));
    expect(screen.getByText('论文搜索')).toBeInTheDocument();
    expect(screen.getByText('我的论文库')).toBeInTheDocument();
    expect(screen.getByText('论文对比')).toBeInTheDocument();
    expect(screen.getByText('候选研究空白')).toBeInTheDocument();
    expect(screen.getByText('备份与恢复')).toBeInTheDocument();
    expect(screen.getByText('管理员配置')).toBeInTheDocument();
  });
});
