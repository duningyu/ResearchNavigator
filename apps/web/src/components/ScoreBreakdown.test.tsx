import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { ScoreBreakdown } from './ScoreBreakdown';

it('uses explicit Chinese labels and never renders unknown internal dimensions', () => {
  const { container } = render(<ScoreBreakdown title="复现条件" score={{
    score: 20, evidence_coverage: 0.2,
    components: { code_availability: null, semantic_similarity: 0.2, executor_private_v9: 1 },
    blocking_reasons: ['data_availability', 'executor_private_v9'],
  }} />);
  expect(screen.getByText('代码可用性')).toBeInTheDocument();
  expect(screen.getByText('词语相近程度（不等于任务相关）')).toBeInTheDocument();
  expect(screen.getByText(/数据可用性/)).toBeInTheDocument();
  expect(container.textContent).not.toMatch(/code_availability|semantic_similarity|executor_private_v9/);
});
