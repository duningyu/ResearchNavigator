import { expect, it } from 'vitest';
import { readingOrder } from './comparisonReading';
import type { ComparisonRun } from '../types/domain';

it('does not rank absent evidence as zero performance and preserves ties', () => {
  const comparison = { papers: [{ id: 1, title: 'A', relation: 'direct' }, { id: 2, title: 'B', relation: 'direct' }], rows: [] } as unknown as ComparisonRun;
  expect(readingOrder(comparison).priority).toEqual([]);
  comparison.rows = [{ key: 'task_definition', label: '任务', cells: [1, 2].map((paper_id) => ({ paper_id, value: 'task', evidence_state: 'evidenced', citations: [{ source_type: 'abstract', supporting_text: 'task' }] })) }] as ComparisonRun['rows'];
  expect(readingOrder(comparison).priority.map((paper) => paper.id)).toEqual([1, 2]);
  expect(readingOrder(comparison).reason).toContain('并列');
});
it('prioritizes traceable reading, not the highest arbitrary metric', () => {
  const comparison = { papers: [{ id: 1, title: 'A', relation: 'direct' }, { id: 2, title: 'B', relation: 'direct' }], rows: [
    { key: 'major_results', cells: [{ paper_id: 1, value: '99.9%', evidence_state: 'evidenced', citations: [] }] },
    { key: 'task_definition', cells: [{ paper_id: 2, value: 'task', evidence_state: 'evidenced', citations: [{ source_type: 'abstract', supporting_text: 'task' }] }] },
  ] } as unknown as ComparisonRun;
  expect(readingOrder(comparison).priority.map((paper) => paper.id)).toEqual([2]);
  expect(readingOrder(comparison).others.map((paper) => paper.id)).toEqual([1]);
});

it.each(['unknown', 'unrelated', undefined])('never promotes %s papers merely for richer evidence', (relation) => {
  const comparison = { papers: [{ id: 1, title: 'A', relation }], rows: [
    { key: 'research_problem', cells: [{ paper_id: 1, value: 'task', evidence_state: 'evidenced', citations: [{ source_type: 'abstract', supporting_text: 'task' }] }] },
  ] } as unknown as ComparisonRun;
  expect(readingOrder(comparison).priority).toEqual([]);
});
