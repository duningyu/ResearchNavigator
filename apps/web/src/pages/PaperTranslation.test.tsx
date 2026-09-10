import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PaperPage } from './PaperPage';

function json(value: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' }, ...init });
}

const paper = {
  id: 7,
  title: 'Translation Boundary Fixture',
  abstract: 'The model reaches 95% accuracy on ImageNet under a limited-data condition.',
  authors: [],
  keywords: [],
  source_urls: [],
  source_provenance: [],
  is_fixture: true,
  abstract_evidence_verified: true,
};

const analysis = {
  id: 1,
  paper_id: 7,
  project_id: null,
  analysis_version: 'structured-v3',
  analysis: {
    evidence_level: 'abstract_only',
    executive_summary: '快速解读：该方法在受限数据条件下报告了一个结果。',
    summary: '内部摘要字段不应直接展示。',
    task_definition: { input: null, output: null, setting: null },
    theoretical_contribution: [], method_innovation: [], research_route: [], inputs: [], outputs: [],
    core_methods: [], new_modules: [], datasets: ['ImageNet'], baselines: [], metrics: ['accuracy'],
    experimental_protocol: [], major_results: [], claimed_contributions: [], future_work_explicit: [],
    limitations_author_stated: [], limitations_inferred: [], research_background: null, research_problem: null,
    methods: [], citations: [], field_states: {}, field_citations: {}, missing_fields: [], warnings: [],
  },
  direction_similarity: { score: 0, evidence_coverage: 0 },
  reproduction_assessment: { score: 0, evidence_coverage: 0 },
};

function renderPage(translation: unknown) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith('/papers/7')) return json(paper);
    if (url.includes('/papers/7/abstract-translation')) return json(translation);
    if (url.endsWith('/papers/7/analysis')) return json(analysis);
    if (url.endsWith('/papers/7/documents')) return json([]);
    if (url.endsWith('/papers/7/authors')) return json([]);
    if (url.endsWith('/papers/7/datasets')) return json([]);
    if (url.endsWith('/papers/7/evidence-workflows')) return json([]);
    if (url.endsWith('/projects')) return json([]);
    return json({ detail: `unexpected request: ${url}` }, { status: 500 });
  });
  render(
    <MemoryRouter initialEntries={['/papers/7']}>
      <Routes><Route path="/papers/:paperId" element={<PaperPage />} /></Routes>
    </MemoryRouter>,
  );
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('abstract translation boundary', () => {
  it('defaults to Chinese, preserves the original, and toggles without refetching search', async () => {
    renderPage({
      paper_id: 7,
      original_abstract: paper.abstract,
      translated_abstract: '在有限数据条件下，该模型达到 95% 的准确率，并使用 ImageNet。',
      status: 'ready',
      source_abstract_sha256: 'source-hash',
      target_language: 'zh-CN',
      pipeline_version: 'stub-v1',
      fallback_reason: null,
    });

    expect(await screen.findByText('在有限数据条件下，该模型达到 95% 的准确率，并使用 ImageNet。')).toBeInTheDocument();
    expect(screen.getByText('快速解读：该方法在受限数据条件下报告了一个结果。')).toBeInTheDocument();
    expect(screen.queryByText('内部摘要字段不应直接展示。')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '查看原文' }));
    expect(screen.getByText(paper.abstract)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看中文' }));
    expect(screen.getByText('在有限数据条件下，该模型达到 95% 的准确率，并使用 ImageNet。')).toBeInTheDocument();
  });

  it('falls back to the original abstract for failed or partial translation', async () => {
    renderPage({
      paper_id: 7,
      original_abstract: paper.abstract,
      translated_abstract: null,
      status: 'partial',
      source_abstract_sha256: 'source-hash',
      target_language: 'zh-CN',
      pipeline_version: 'stub-v1',
      fallback_reason: 'partial_translation',
    });

    expect(await screen.findByText(paper.abstract)).toBeInTheDocument();
    expect(screen.getByText('中文译文暂未生成，以下为论文原始摘要。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看中文' })).toBeDisabled();
    expect(screen.queryByText(/translated_abstract|translation_status|fallback_reason/)).not.toBeInTheDocument();
  });
});
