import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { EvidenceWorkflowPanel } from './EvidenceWorkflowPanel';
import type { EvidenceWorkflow } from '../types/domain';

afterEach(cleanup);
it('shows partial acquisition as limited material, never executor JSON or complete text', () => {
  const workflow = { id: 999, status: 'partial', strongest_evidence: 'abstract_only', terminal: true,
    attempt_count: 1, max_attempts: 3, started_at: null, finished_at: null, cancelled_at: null,
    result: { warnings: ['oa_no_eligible_candidate'], source_status: { arxiv: { status: 'rate_limited', detail: 'INTERNAL_DETAIL' } } },
    error: null, events: [{ id: 1, event_type: 'llm_analysis', created_at: '2026-09-06', detail: { executor: 'INTERNAL_EXECUTOR', token: 'DO_NOT_RENDER' } }],
  } as unknown as EvidenceWorkflow;
  render(<EvidenceWorkflowPanel workflow={workflow} busy={false} onRun={vi.fn()} onCancel={vi.fn()} onRefresh={vi.fn()} />);
  expect(screen.getByText('部分步骤未完成')).toBeInTheDocument();
  expect(screen.getByText(/未能取得正文不表示论文收费/)).toBeInTheDocument();
  expect(screen.getByText(/来源暂时限流/)).toBeInTheDocument();
  for (const internal of ['abstract_only', 'partial', 'terminal', 'INTERNAL_DETAIL', 'INTERNAL_EXECUTOR', 'DO_NOT_RENDER', '#999', 'llm_analysis']) {
    expect(document.body.textContent).not.toContain(internal);
  }
});
