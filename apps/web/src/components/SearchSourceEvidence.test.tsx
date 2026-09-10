import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { SearchSourceEvidence } from './SearchSourceEvidence';

afterEach(cleanup);
it('shows observed time and effective query without equating search with full text', () => {
  render(<SearchSourceEvidence name="arxiv" status={{ status: 'ok', result_count: 0,
    checked_at: '2026-09-06T08:00:00Z', metadata: { executed_query: 'future window early warning',
      query_adaptation: 'controlled_glossary', debug_secret: 'DO-NOT-RENDER' } }} />);
  expect(screen.getByText(/已响应，未找到匹配结果/)).toBeInTheDocument();
  expect(screen.getByText(/future window early warning/)).toBeInTheDocument();
  expect(screen.getByText(/2026-09-06/)).toBeInTheDocument();
  expect(screen.getByText(/不代表全文可获取/)).toBeInTheDocument();
  expect(screen.queryByText(/DO-NOT-RENDER/)).not.toBeInTheDocument();
});
it('does not invent a check time or translate an unknown status', () => {
  render(<SearchSourceEvidence name="arxiv" status={{ status: 'disabled' }} />);
  expect(screen.getByText(/未启用/)).toBeInTheDocument();
  expect(screen.getByText(/未提供本次检查时间/)).toBeInTheDocument();
});

it('explains that a controlled English query was added', () => {
  render(<SearchSourceEvidence name="arxiv" status={{ status: 'ok', result_count: 1,
    metadata: { query_adaptation_status: 'ADAPTED', query_adaptation_used_fallback: false } }} />);
  expect(screen.getByText('已补充英文检索词')).toBeInTheDocument();
  expect(screen.queryByText(/ADAPTED/)).not.toBeInTheDocument();
});

it('explains safe fallback while keeping the original query path available', () => {
  render(<SearchSourceEvidence name="arxiv" status={{ status: 'ok', result_count: 1,
    metadata: { query_adaptation_status: 'FALLBACK_ORIGINAL', query_adaptation_used_fallback: true } }} />);
  expect(screen.getByText('英文检索词暂未生成，已使用原关键词继续搜索')).toBeInTheDocument();
  expect(screen.queryByText(/FALLBACK_ORIGINAL/)).not.toBeInTheDocument();
});
