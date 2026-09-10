import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { ComparePage } from './ComparePage';

vi.mock('../components/PaperSelectionPanel', () => ({ PaperSelectionPanel: ({ onChange }: { onChange: (papers: unknown[]) => void }) => <button onClick={() => onChange([{ id: 1 }, { id: 2 }])}>选择测试论文</button> }));
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it('reloads an exact saved comparison without creating another result', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => new Response(JSON.stringify(String(input).endsWith('/projects') ? [{ id: 1, name: '研究方向' }] : { id: 8, project_id: 1, paper_set_id: 2, papers: [{ id: 1, title: 'Saved original title', evidence_level: 'abstract_only' }], rows: [] }), { headers: { 'Content-Type': 'application/json' } }));
  render(<MemoryRouter initialEntries={['/compare?project=1&paperSet=2&comparison=8']}><ComparePage /></MemoryRouter>);
  expect(await screen.findByText('先看结论')).toBeInTheDocument();
  expect(screen.getAllByText('Saved original title').length).toBeGreaterThan(0);
  expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === 'GET')).toBe(true);
});
it('does not display a saved comparison belonging to a different selected project', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => new Response(JSON.stringify(String(input).endsWith('/projects') ? [] : { id: 8, project_id: 9, paper_set_id: 2, papers: [], rows: [] }), { headers: { 'Content-Type': 'application/json' } }));
  render(<MemoryRouter initialEntries={['/compare?project=1&paperSet=2&comparison=8']}><ComparePage /></MemoryRouter>);
  expect(await screen.findByText('已保存对比与当前方向或论文集合不一致，请重新选择。')).toBeInTheDocument();
  expect(screen.queryByText('先看结论')).not.toBeInTheDocument();
});
it('opens research opportunities in the shared workspace with the selected direction', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => new Response(JSON.stringify(String(input).endsWith('/projects') ? [{ id: 2, name: '图像分割方向' }] : []), { headers: { 'Content-Type': 'application/json' } }));
  render(<MemoryRouter initialEntries={['/compare?tab=opportunities&project=2']}><ComparePage /></MemoryRouter>);
  expect(await screen.findByRole('tab', { name: '核实研究机会', selected: true })).toBeInTheDocument();
  expect(await screen.findByText('图像分割方向')).toBeInTheDocument();
  expect(screen.getByText('候选研究空白是待核实的研究假设，不是创新性证明')).toBeInTheDocument();
});
it('presents a conservative conclusion before the matrix without raw executor fields', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = String(input);
    const result = path.endsWith('/projects') ? [{ id: 1, name: '研究方向' }]
      : path.endsWith('/paper-sets') ? { id: 2 }
      : { id: 999, paper_set_id: 2, project_id: 1, analysis_version: 'INTERNAL_VERSION', evidence_hash: 'SECRET_INTERNAL_HASH',
        papers: [{ id: 1, title: 'Original English Title', evidence_level: 'abstract_only' }, { id: 2, title: 'Second Paper', evidence_level: 'metadata_only' }],
        rows: [{ key: 'task_definition', label: '研究任务', cells: [
          { paper_id: 1, value: { input: 'image', executor: 'INTERNAL_EXECUTOR' }, evidence_state: 'evidenced', citations: [{}] },
          { paper_id: 2, value: null, evidence_state: 'insufficient_evidence', citations: [] },
        ] }] };
    return new Response(JSON.stringify(result), { headers: { 'Content-Type': 'application/json' } });
  });
  render(<MemoryRouter><ComparePage /></MemoryRouter>);
  await screen.findByRole('button', { name: '选择测试论文' });
  fireEvent.mouseDown(screen.getAllByRole('combobox')[0]);
  fireEvent.click(await screen.findByText('研究方向'));
  fireEvent.click(screen.getByRole('button', { name: '选择测试论文' }));
  fireEvent.click(screen.getByRole('button', { name: '生成证据级对比矩阵' }));
  expect(await screen.findByText('先看结论')).toBeInTheDocument();
  expect(screen.getByText(/尚不能据此判断方法优劣/)).toBeInTheDocument();
  expect(screen.getAllByText('Original English Title').length).toBeGreaterThan(0);
  for (const internal of ['INTERNAL_VERSION', 'INTERNAL_EXECUTOR', 'abstract_only', 'insufficient_evidence', 'SECRET_INTERNAL_HASH']) {
    expect(document.body.textContent).not.toContain(internal);
  }
  expect(screen.getByRole('link', { name: '继续核实研究机会' })).toHaveAttribute('href', '/gaps?project=1&paperSet=2');
});
