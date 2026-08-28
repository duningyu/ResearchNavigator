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
  it('renders terminal status, strongest evidence, source failure and event timeline', () => {
    render(<EvidenceWorkflowPanel workflow={workflow} busy={false} onRun={vi.fn()} onCancel={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByText('partial')).toBeInTheDocument();
    const evidenceRow = screen.getByText('最终证据等级').closest('tr');
    expect(evidenceRow).not.toBeNull();
    expect(within(evidenceRow as HTMLElement).getByText('abstract_only')).toBeInTheDocument();
    expect(screen.getByText(/OpenAlex rate limited/)).toBeInTheDocument();
    expect(screen.getByText(/HTTP 429/)).toBeInTheDocument();
    expect(screen.getByText('abstract_acquisition')).toBeInTheDocument();
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
