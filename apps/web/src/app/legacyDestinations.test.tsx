import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from './App';

vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ token: 'synthetic', user: { id: 1, is_admin: false } }) }));
vi.mock('../components/BackendAvailabilityGate', () => ({ BackendAvailabilityGate: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../pages/DashboardPage', () => ({ DashboardPage: () => <h1>研究首页正文</h1> }));
vi.mock('../pages/ComparePage', () => ({ ComparePage: () => <output>{useLocation().pathname}{useLocation().search}</output> }));
vi.mock('../pages/JobsPage', () => ({ JobsPage: () => <h1>独立任务页</h1> }));
vi.mock('../pages/DirectionMapPage', () => ({ DirectionMapPage: () => <h1>独立聚类页</h1> }));
vi.mock('../pages/EvaluationsPage', () => ({ EvaluationsPage: () => <h1>独立专家页</h1> }));
afterEach(cleanup);
it('旧空白地址只携带合法项目与集合进入统一研究机会页', async () => {
  render(<MemoryRouter initialEntries={['/gaps?project=2&paperSet=3&token=discard&session=4']}><App /></MemoryRouter>);
  expect(await screen.findByText('/compare?tab=opportunities&project=2&paperSet=3')).toBeInTheDocument();
});
it('旧空白地址拒绝不合法的上下文编号', async () => {
  render(<MemoryRouter initialEntries={['/gaps?project=-2&paperSet=NaN']}><App /></MemoryRouter>);
  expect(await screen.findByText('/compare?tab=opportunities')).toBeInTheDocument();
});
it.each(['/jobs', '/direction-map', '/evaluations'])('旧普通用户地址 %s 不再暴露独立内部页面', async (path) => {
  render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
  expect(await screen.findByRole('heading', { name: '研究首页正文' })).toBeInTheDocument();
  expect(screen.queryByText(/独立.*页/)).not.toBeInTheDocument();
});
