import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ReadingRecommendationCard } from './ReadingRecommendationCard';

describe('ReadingRecommendationCard', () => {
  it('renders Chinese verdict and evidence without internal enums', () => {
    render(
      <ReadingRecommendationCard
        recommendation={{
          verdict: 'method_reference',
          rationale: '研究任务不同，但方法可能具有参考价值。',
          task_match: 'mismatched',
          evidence_level: 'abstract',
          applicability: '可作为方法参考。',
          missing_information: ['需要正文核实实验设置'],
          evidence_refs: [{ paper_identity: 'arxiv:2603.29261v1', material_identity: 'abstract:abc' }],
          research_profile_identity: 'profile:abc',
          paper_identity: 'arxiv:2603.29261v1',
          material_identity: 'abstract:abc',
          is_current: true,
        }}
      />,
    );

    expect(screen.getByText('阅读建议')).toBeInTheDocument();
    expect(screen.getByText('方法参考')).toBeInTheDocument();
    expect(screen.getByText('研究任务不同，但方法可能具有参考价值。')).toBeInTheDocument();
    expect(screen.getByText('需要正文核实实验设置')).toBeInTheDocument();
    expect(screen.queryByText('method_reference')).not.toBeInTheDocument();
    expect(screen.queryByText('reading_recommendation')).not.toBeInTheDocument();
  });
});
