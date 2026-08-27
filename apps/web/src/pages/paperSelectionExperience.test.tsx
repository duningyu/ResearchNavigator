import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PaperSelectionPanel } from '../components/PaperSelectionPanel';
import { SearchPage } from './SearchPage';

const papers = [
  { id: 41, title: 'Evidence-Aware Industrial Anomaly Detection', authors: [], keywords: ['anomaly detection'], source_urls: [], source_provenance: [], is_fixture: false, publication_year: 2025, venue: 'TSAD', ranking: { label: 'frontier_candidate', relevance: .91, rank_score: .91, relevance_band: 9, position: 1 } },
  { id: 42, title: 'Forecasting Maintenance Windows', authors: [], keywords: ['maintenance'], source_urls: [], source_provenance: [], is_fixture: false, publication_year: 2024, venue: 'KDD', ranking: { label: 'classic_candidate', relevance: .88, rank_score: .88, relevance_band: 8, position: 2 } },
];

function json(value: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' }, ...init });
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('selection-first paper workflow', () => {
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
    render(<MemoryRouter initialEntries={['/search?session=7&page=1']}><SearchPage /></MemoryRouter>);

    expect(await screen.findByText('Attention paper 1')).toBeInTheDocument();
    expect(screen.getByText('Attention paper 10')).toBeInTheDocument();
    expect(screen.queryByText('Attention paper 11')).not.toBeInTheDocument();
    expect(screen.getByText('mode=discovery')).toBeInTheDocument();
    expect(screen.getByText('classic=10 · frontier=40 · shortfall=0/0')).toBeInTheDocument();
  });
});
