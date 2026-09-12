import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { PlansPage } from './PlansPage';

vi.mock('../api/client', () => ({
  apiRequest: vi.fn().mockResolvedValue([{
    id: 7, project_id: 3, gap_id: null, plan_kind: 'reading', title: '已有阅读计划',
    objective: '已有计划目标', status: 'active', review_required: false, review_reason: null,
    items: [], created_at: '2026-09-13T00:00:00Z',
  }]),
}));

afterEach(() => cleanup());

describe('PlansPage', () => {
  it('keeps all plan creation actions visible when plans already exist', async () => {
    render(<MemoryRouter initialEntries={['/plans?project=3']}><PlansPage /></MemoryRouter>);

    expect(await screen.findByRole('button', { name: '创建阅读计划' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '创建探索计划' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '手动添加行动' })).toBeInTheDocument();
  });
});
