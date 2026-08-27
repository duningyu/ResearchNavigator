import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PaperPage } from './PaperPage';

function json(value: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' }, ...init });
}

const paper = {
  id: 7,
  title: 'Evidence Acquisition for Industrial Alerts',
  abstract: null,
  authors: [],
  keywords: [],
  source_urls: [],
  source_provenance: [],
  is_fixture: false,
};

function analysis(evidenceLevel: 'metadata_only' | 'abstract_only', summary: string) {
  const emptyFields = {
    research_background: null,
    research_problem: null,
    task_definition: { input: null, output: null, setting: null },
    theoretical_contribution: [],
    method_innovation: [],
    research_route: [],
    inputs: [],
    outputs: [],
    core_methods: [],
    new_modules: [],
    datasets: [],
    baselines: [],
    metrics: [],
    experimental_protocol: [],
    major_results: [],
    claimed_contributions: [],
    future_work_explicit: [],
    limitations_author_stated: [],
    limitations_inferred: [],
    methods: [],
  };
  const fieldNames = ['executive_summary', ...Object.keys(emptyFields)];
  return {
    id: evidenceLevel === 'metadata_only' ? 1 : 2,
    paper_id: 7,
    project_id: null,
    analysis_version: 'structured-v3',
    analysis: {
      evidence_level: evidenceLevel,
      executive_summary: summary,
      summary,
      ...emptyFields,
      citations: [],
      field_states: Object.fromEntries(fieldNames.map((field) => [field, field === 'executive_summary' ? 'evidenced' : 'unknown'])),
      field_citations: Object.fromEntries(fieldNames.map((field) => [field, []])),
      missing_fields: [],
      warnings: ['当前仅有元数据，结构化分析能力受限。'],
    },
    direction_similarity: { score: 0, evidence_coverage: 0 },
    reproduction_assessment: { score: 0, evidence_coverage: 0 },
  };
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('paper evidence acquisition', () => {
  it('shows abstention values, renders an empty missing-field set as none, and explicitly acquires evidence', async () => {
    const initial = analysis('metadata_only', paper.title);
    const enriched = analysis('abstract_only', 'Concrete abstract evidence');
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/papers/7/acquire-evidence') && init?.method === 'POST') {
        return json({
          run_id: 'run-7',
          outcome: 'abstract_acquired',
          evidence_level_before: 'metadata_only',
          evidence_level_after: 'abstract_only',
          queried_sources: ['crossref'],
          source_status: { crossref: { status: 'ok', result_count: 1 } },
          paper: { ...paper, abstract: 'Concrete abstract evidence' },
          analysis: enriched,
        });
      }
      if (url.endsWith('/papers/7/analysis')) return json(initial);
      if (url.endsWith('/papers/7/documents')) return json([]);
      if (url.endsWith('/papers/7')) return json(paper);
      if (url.endsWith('/projects')) return json([]);
      return json({ detail: `unexpected request: ${url}` }, { status: 500 });
    });
    render(
      <MemoryRouter initialEntries={['/papers/7']}>
        <Routes><Route path="/papers/:paperId" element={<PaperPage />} /></Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('证据等级：metadata_only')).toBeInTheDocument();
    expect(screen.getAllByText('未在当前可访问文本中找到。').length).toBeGreaterThan(0);
    expect(screen.getByText('缺失字段').closest('tr')).toHaveTextContent('无');

    fireEvent.click(screen.getByRole('button', { name: '获取更多证据并重新分析' }));

    expect(await screen.findByText('证据等级：abstract_only')).toBeInTheDocument();
    expect(screen.getAllByText('Concrete abstract evidence').length).toBeGreaterThan(0);
    expect(screen.getByText('crossref: ok')).toBeInTheDocument();
    await waitFor(() => expect(fetchSpy.mock.calls.some(([input]) => String(input).endsWith('/papers/7/acquire-evidence'))).toBe(true));
  });
});
