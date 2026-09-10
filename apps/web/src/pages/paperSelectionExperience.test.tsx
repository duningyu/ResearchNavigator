import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PaperSelectionPanel } from '../components/PaperSelectionPanel';
import { SearchPage } from './SearchPage';
import { AuthProvider } from '../auth/AuthContext';

const papers = [
  { id: 41, title: 'Evidence-Aware Industrial Anomaly Detection', authors: [], keywords: ['anomaly detection'], source_urls: [], source_provenance: [], is_fixture: false, publication_year: 2025, venue: 'TSAD', ranking: { label: 'frontier_candidate', relevance: .91, rank_score: .91, relevance_band: 9, position: 1 } },
  { id: 42, title: 'Forecasting Maintenance Windows', authors: [], keywords: ['maintenance'], source_urls: [], source_provenance: [], is_fixture: false, publication_year: 2024, venue: 'KDD', ranking: { label: 'classic_candidate', relevance: .88, rank_score: .88, relevance_band: 8, position: 2 } },
];

function json(value: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' }, ...init });
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('selection-first paper workflow', () => {
  it('submits an edited source query without replacing the original research question', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({}, { status: 503 }));
    render(<AuthProvider><MemoryRouter><SearchPage /></MemoryRouter></AuthProvider>);
    fireEvent.change(screen.getByPlaceholderText('关键词、题目、DOI、arXiv ID、作者或数据集'), { target: { value: '图像语义分割' } });
    fireEvent.change(screen.getByLabelText('arXiv 检索式'), { target: { value: 'ti:"segmentation"' } });
    fireEvent.click(screen.getByRole('checkbox', { name: '使用受控术语表适配中英检索' }));
    fireEvent.click(screen.getByRole('button', { name: /搜\s*索/ }));
    await waitFor(() => expect(fetchSpy.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true));
    const request = fetchSpy.mock.calls.find(([, init]) => init?.method === 'POST')!;
    expect(JSON.parse(String(request[1]?.body))).toMatchObject({ query: '图像语义分割', adapt_query: false, source_queries: { arxiv: 'ti:"segmentation"' } });
  });
  it('discards a late initial paper set after switching to favourites', async () => {
    let resolveSet!: (response: Response) => void;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).endsWith('/paper-sets/8')) return new Promise<Response>((resolve) => { resolveSet = resolve; });
      return json({ items: [{ paper: papers[1], favorite: true }] });
    });
    const onChange = vi.fn();
    render(<MemoryRouter><PaperSelectionPanel purpose="compare" ariaLabel="选择论文" initialPaperSetId={8} selected={[]} onChange={onChange} /></MemoryRouter>);
    fireEvent.click(screen.getByRole('radio', { name: '题名检索' }));
    fireEvent.click(screen.getByRole('radio', { name: '收藏论文' }));
    expect(await screen.findByText(papers[1].title)).toBeInTheDocument();
    await act(async () => resolveSet(json({ papers: [papers[0]] })));
    expect(screen.queryByText(papers[0].title)).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });
  it('refuses a URL session from a different project before rendering results', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => json(String(input).endsWith('/papers') ? papers : {
      id: 7, project_id: 99, query: 'other project', filters: {}, source_status: {},
      result_ids: [41, 42], result_count: 2, search_mode: 'precise', composition: {},
    }));
    render(<AuthProvider><MemoryRouter initialEntries={['/search?session=7&project=1']}><SearchPage /></MemoryRouter></AuthProvider>);
    expect(await screen.findByText('此检索现场不属于当前项目，请在当前项目重新检索。')).toBeInTheDocument();
    expect(screen.queryByText(papers[0].title)).not.toBeInTheDocument();
  });
  it('loads the explicitly requested search session and never assumes the newest session', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/search/sessions/8/papers')) return json(papers);
      return json({ detail: `unexpected request: ${url}` }, { status: 500 });
    });
    render(<MemoryRouter><PaperSelectionPanel purpose="compare" ariaLabel="选择论文" initialSessionId={8} selected={[]} onChange={() => undefined} /></MemoryRouter>);

    expect(await screen.findByText('Evidence-Aware Industrial Anomaly Detection')).toBeInTheDocument();
    expect(fetchSpy.mock.calls.some(([input]) => String(input).endsWith('/search/sessions'))).toBe(false);
  });

  it('uses saved favourites as an explicit selection source', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).endsWith('/library')) return json({ items: [{ paper: papers[0], favorite: true, notes: [], tags: [], reading_status: null }] });
      return json([]);
    });
    render(<MemoryRouter><PaperSelectionPanel purpose="gap" ariaLabel="选择论文" selected={[]} onChange={() => undefined} /></MemoryRouter>);
    fireEvent.click(screen.getByRole('radio', { name: '收藏论文' }));
    expect(await screen.findByText('Evidence-Aware Industrial Anomaly Detection')).toBeInTheDocument();
  });

  it('restores a persisted Top50 search session and paginates ten papers per page', async () => {
    const fifty = Array.from({ length: 50 }, (_, index) => ({ ...papers[0], id: index + 1, title: `Attention paper ${index + 1}`, ranking: { label: index < 10 ? 'classic_candidate' : 'frontier_candidate', relevance: .9 - index / 100, rank_score: .9 - index / 100, relevance_band: 9, position: index + 1 } }));
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/search/sessions/7')) return json({ id: 7, project_id: null, query: 'attention', filters: { limit: 50 }, source_status: {}, result_ids: fifty.map((paper) => paper.id), result_count: 50, search_mode: 'discovery', diversity_seed: 'seed-7', ranking_rule_version: 'discovery-ranking-v1', composition: { classic_count: 10, frontier_count: 40 }, created_at: '2026-08-27T00:00:00Z' });
      if (url.endsWith('/search/sessions/7/papers')) return json(fifty);
      return json([]);
    });
    render(<AuthProvider><MemoryRouter initialEntries={['/search?session=7&page=1']}><SearchPage /></MemoryRouter></AuthProvider>);

    expect(await screen.findByText('Attention paper 1')).toBeInTheDocument();
    expect(screen.getByText('Attention paper 10')).toBeInTheDocument();
    expect(screen.queryByText('Attention paper 11')).not.toBeInTheDocument();
    expect(screen.getAllByText('探索相关论文').length).toBeGreaterThan(0);
    expect(screen.getByText('经典候选 10 篇 · 前沿候选 40 篇 · 数量缺口 0 / 0')).toBeInTheDocument();
    expect(screen.queryByText('mode=discovery')).not.toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: '选择 Attention paper 1' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: '选择 Attention paper 1' }));
    fireEvent.click(screen.getByRole('checkbox', { name: '选择 Attention paper 3' }));
    expect(screen.getByRole('link', { name: '比较所选论文' })).toHaveAttribute('href', '/compare?session=7&papers=1%2C3');
  });

  it('hydrates only explicitly chosen IDs from an owned search session', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(papers));
    const onChange = vi.fn();
    render(<MemoryRouter><PaperSelectionPanel purpose="compare" ariaLabel="选择论文" initialSessionId={8} initialSelectedIds={[42, 999]} selected={[]} onChange={onChange} /></MemoryRouter>);
    await waitFor(() => expect(onChange).toHaveBeenCalledWith([papers[1]]));
  });
});
