import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ScoreBreakdown } from './ScoreBreakdown';

describe('ScoreBreakdown', () => {
  it('renders reproduction readiness without a fake zero score', () => {
    render(<ScoreBreakdown title="复现准备情况" score={{
      score: null,
      evidence_coverage: 0.35,
      dimensions: [
        { name: 'method_completeness', status: 'partial', score: 0.45, evidence: '仅依据摘要。' },
        { name: 'code_availability', status: 'unknown', score: null, evidence: '尚未核验。' },
      ],
      recommended_first_step: '先检查作者代码仓库和数据集入口。',
    }} />);
    expect(screen.getByText('复现准备情况')).toBeInTheDocument();
    expect(screen.getByText('信息不足，暂不评分')).toBeInTheDocument();
    expect(screen.getByText('建议下一步')).toBeInTheDocument();
    expect(screen.getByText('先检查作者代码仓库和数据集入口。')).toBeInTheDocument();
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
  });

  it('explains that low-coverage direction matching is preliminary', () => {
    render(<ScoreBreakdown title="与当前研究课题的匹配度" score={{
      score: 0.72,
      evidence_coverage: 0.6,
      components: { semantic_similarity: 0.72 },
    }} />);
    expect(screen.getByText('初步判断')).toBeInTheDocument();
    expect(screen.getByText('当前结果基于研究课题、论文元数据/摘要和已获得证据；补充正文后结论可能变化。')).toBeInTheDocument();
  });
});
