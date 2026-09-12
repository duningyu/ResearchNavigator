import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { GapsPage } from './GapsPage';
import { PlansPage } from './PlansPage';

vi.mock('../components/PaperSelectionPanel', () => ({
  PaperSelectionPanel: ({ onChange }: { onChange: (papers: Array<{ id: number; title: string }>) => void }) => (
    <button type="button" onClick={() => onChange([{ id: 101, title: 'TranAD fixture' }])}>选择测试证据论文</button>
  ),
}));

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it('links gap evidence to its exact paper, project and cited excerpt', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => new Response(JSON.stringify(String(input).endsWith('/gaps') ? [{
    id: 9, project_id: 7, status: 'candidate', claim: '需要核实的研究问题', scope: '图像分割', minimal_validation: [], risk_factors: [],
    explanation: { direct_evidence: [{ paper_id: 42, title: 'Original title', source_type: 'fulltext', chunk_id: 8, supporting_text: 'Future work requires independent evaluation.' }], inferences: [], absent_evidence: [], novelty_risk_factors: [] },
  }] : [])));
  render(<MemoryRouter><GapsPage /></MemoryRouter>);
  const link = await screen.findByRole('link', { name: '定位原文依据' });
  const target = new URL(link.getAttribute('href')!, 'https://example.invalid');
  expect(target.pathname).toBe('/papers/42');
  expect(target.searchParams.get('project')).toBe('7');
  expect(target.searchParams.get('evidenceChunk')).toBe('8');
  expect(target.searchParams.get('quote')).toBe('Future work requires independent evaluation.');
});
it('offers editable steps, skip and reopen without treating self-report as evidence', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(JSON.stringify([{ id: 1, title: '核验计划', objective: '核对原文',
    items: [{ id: 2, title: '原文对照', category: 'baseline', status: 'done', description: '输出对照表' }] }]), { headers: { 'Content-Type': 'application/json' } }));
  render(<MemoryRouter><PlansPage /></MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', { name: '重新打开' }));
  await waitFor(() => expect(fetcher.mock.calls.some(([, init]) => init?.method === 'PUT' && JSON.parse(String(init.body)).status === 'pending')).toBe(true));
  expect(screen.getByText('完成状态由你记录，不代表研究结论已验证。')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '编辑步骤' })).toBeInTheDocument();
  expect(screen.getByText('行动目的：未填写')).toBeInTheDocument();
  expect(screen.getByText('预期产出：未填写')).toBeInTheDocument();
});
it('keeps legacy gaps review-only and hides executor/JSON state', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => new Response(JSON.stringify(String(input).endsWith('/gaps') ? [{
    id: 9, project_id: 1, paper_set_id: 12, status: 'confirmed', workflow_stage: 'executor_internal',
    confidence: 'low', claim: '原有候选', scope: '图像语义分割', suggested_research_question: '需要重新核对材料',
    not_novelty_proof: true, minimal_validation: [], risk_factors: [], review_required: true, review_reason: '材料已变化，请重新核验',
  }] : []), { headers: { 'Content-Type': 'application/json' } }));
  render(<MemoryRouter><GapsPage /></MemoryRouter>);
  expect(await screen.findByText('材料已变化，请重新核验')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '创建研究计划' })).toBeDisabled();
  expect(screen.queryByText('executor_internal')).not.toBeInTheDocument();
  expect(screen.queryByText('not_novelty_proof=true')).not.toBeInTheDocument();
});
it('prevents completing stale plans and explains why', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify([{ id: 1, title: '核验计划', objective: '核对原文',
    review_required: true, review_reason: '候选需要复核', items: [{ id: 2, title: '对照', category: 'baseline', status: 'pending', description: '复核相同条件' }] }]), { headers: { 'Content-Type': 'application/json' } }));
  render(<MemoryRouter><PlansPage /></MemoryRouter>);
  expect(await screen.findByText('候选需要复核')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /完\s*成/ })).toBeDisabled();
  expect(screen.getByText('建立对照')).toBeInTheDocument();
});

it('renders an evidence decision instead of exposing a 409 gap error', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith('/projects')) return new Response(JSON.stringify([{ id: 1, name: '工业时序预警' }]), { headers: { 'Content-Type': 'application/json' } });
    if (url.endsWith('/gaps')) return new Response('[]', { headers: { 'Content-Type': 'application/json' } });
    if (url.endsWith('/paper-sets') && init?.method === 'POST') return new Response(JSON.stringify({ id: 12, project_id: 1, papers: [] }), { headers: { 'Content-Type': 'application/json' } });
    if (url.endsWith('/gaps/generate')) return new Response(JSON.stringify({ detail: { reason: '当前证据还不足以确认一个可靠的研究空白。', actions: ['补充更直接相关的论文', '查看当前证据差异', '保存当前比较结果'] } }), { status: 409, headers: { 'Content-Type': 'application/json' } });
    return new Response('[]', { headers: { 'Content-Type': 'application/json' } });
  });
  render(<MemoryRouter initialEntries={['/?project=1']}><GapsPage /></MemoryRouter>);

  fireEvent.click(await screen.findByRole('button', { name: '选择测试证据论文' }));
  fireEvent.click(screen.getByRole('button', { name: '构建证据矩阵并解释候选空白' }));

  await waitFor(() => expect(screen.getByText('当前证据还不足以确认一个可靠的研究空白。')).toBeInTheDocument());
  expect(screen.getByRole('button', { name: '补充更多论文' })).toBeInTheDocument();
  expect(screen.queryByText('候选研究空白流程失败')).not.toBeInTheDocument();
  expect(screen.queryByText('INSUFFICIENT_RELEVANT_CITED_EVIDENCE')).not.toBeInTheDocument();
  expect(screen.queryByText('409')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '我已人工审阅并确认' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '创建研究计划' })).not.toBeInTheDocument();
  expect(fetcher.mock.calls.some(([input, init]) => String(input).endsWith('/gaps/generate') && init?.method === 'POST')).toBe(true);
});
