import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EvidenceWorkflowPanel } from './EvidenceWorkflowPanel';
import type { EvidenceWorkflow } from '../types/domain';

const workflow: EvidenceWorkflow = {
  id: 31,
  paper_id: 7,
  project_id: 2,
  status: 'partial',
  payload: {},
  result: { warnings: ['OpenAlex rate limited'], source_status: { openalex: { status: 'rate_limited' } } },
  error: null,
  strongest_evidence: 'abstract_only',
  attempt_count: 1,
  max_attempts: 3,
  started_at: '2026-08-28T01:00:00Z',
  finished_at: '2026-08-28T01:01:00Z',
  cancelled_at: null,
  created_at: '2026-08-28T01:00:00Z',
  terminal: true,
  events: [
    { id: 1, event_type: 'abstract_acquisition', detail: { outcome: 'abstract_acquired', evidence_after: 'abstract_only' }, created_at: '2026-08-28T01:00:10Z' },
    { id: 2, event_type: 'oa_location_discovery', detail: { error: 'HTTP 429' }, created_at: '2026-08-28T01:00:20Z' },
  ],
};

afterEach(cleanup);

describe('EvidenceWorkflowPanel', () => {
  it('does not present a success flag without verified result as completion', () => {
    render(<EvidenceWorkflowPanel workflow={{ ...workflow, status: 'succeeded', result: {}, result_integrity: 'missing_or_mismatched' }} busy={false} onRun={vi.fn()} onCancel={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByText('结果尚未核验')).toBeInTheDocument();
    expect(screen.queryByText('处理完成')).not.toBeInTheDocument();
  });
  it('renders terminal status, strongest evidence, source failure and event timeline', () => {
    render(<EvidenceWorkflowPanel workflow={workflow} busy={false} onRun={vi.fn()} onCancel={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByText('部分步骤未完成')).toBeInTheDocument();
    const evidenceRow = screen.getByText('现有材料').closest('tr');
    expect(evidenceRow).not.toBeNull();
    expect(within(evidenceRow as HTMLElement).getByText('仅摘要')).toBeInTheDocument();
    expect(screen.getByText('openalex: 来源暂时限流')).toBeInTheDocument();
    expect(screen.getByText('材料仍有缺口')).toBeInTheDocument();
    expect(screen.getByText('获取摘要')).toBeInTheDocument();
    expect(screen.queryByText('abstract_acquisition')).not.toBeInTheDocument();
    expect(screen.queryByText('HTTP 429')).not.toBeInTheDocument();
  });

  it('allows a pending workflow to run or be cancelled', () => {
    const onRun = vi.fn();
    const onCancel = vi.fn();
    render(<EvidenceWorkflowPanel workflow={{ ...workflow, status: 'pending', terminal: false, events: [] }} busy={false} onRun={onRun} onCancel={onCancel} onRefresh={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '运行证据工作流' }));
    fireEvent.click(screen.getByRole('button', { name: '取消工作流' }));
    expect(onRun).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
