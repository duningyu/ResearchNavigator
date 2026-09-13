import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { PaperAnalysisBody } from '../types/domain';
import { QuickInterpretationPanel } from './QuickInterpretationPanel';

const baseAnalysis = {
  evidence_level: 'abstract_only',
  quick_interpretation_zh: {
    overview: '这是一项摘要级初步分析。',
    background: null,
    problem: '论文研究多变量时间序列异常检测。',
    task: null,
    method: '作者使用 Transformer 方法。',
    result: null,
  },
  field_citations: {
    research_problem: [{ source_type: 'abstract', supporting_text: 'The paper studies multivariate time series anomaly detection.' }],
    core_methods: [
      { source_type: 'abstract', supporting_text: 'The paper studies multivariate time series anomaly detection.' },
      { source_type: 'abstract', supporting_text: 'The authors use a Transformer method.' },
    ],
  },
} as unknown as PaperAnalysisBody;

describe('QuickInterpretationPanel', () => {
  it('shows Chinese interpretation first and keeps original evidence collapsed', () => {
    render(<QuickInterpretationPanel analysis={baseAnalysis} />);

    expect(screen.getByText('快速解读')).toBeInTheDocument();
    expect(screen.getByText('这是一项摘要级初步分析。')).toBeInTheDocument();
    expect(screen.getByText('当前材料：摘要级初步分析')).toBeInTheDocument();
    expect(screen.queryByText('The paper studies multivariate time series anomaly detection.')).not.toBeInTheDocument();
  });

  it('reveals each duplicate original citation only once', () => {
    render(<QuickInterpretationPanel analysis={baseAnalysis} />);

    fireEvent.click(screen.getAllByRole('button', { name: '查看原文证据' })[0]);
    expect(screen.getAllByText('The paper studies multivariate time series anomaly detection.')).toHaveLength(1);
    expect(screen.getAllByText('来源：Abstract')).toHaveLength(2);
  });

  it('keeps original evidence accessible when Chinese interpretation is unavailable', () => {
    render(<QuickInterpretationPanel analysis={{ ...baseAnalysis, quick_interpretation_zh: null }} />);

    expect(screen.getByText('中文快速解读暂不可用')).toBeInTheDocument();
    expect(screen.getByText('查看原始证据')).toBeInTheDocument();
  });
});
