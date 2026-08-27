import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DirectionMapPage } from './DirectionMapPage';

function json(value: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' }, ...init });
}

const paper = (id: number, title: string) => ({
  paper: { id, title, authors: [], keywords: [], source_urls: [], source_provenance: [], is_fixture: false, abstract_evidence_verified: true },
  favorite: true,
  notes: [],
  tags: [],
  reading_status: null,
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('DirectionMapPage', () => {
  it('clusters explicitly selected favorite papers and always shows the classification disclaimer', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/projects')) return json([{ id: 1, name: 'TSAD', status: 'active' }]);
      if (url.endsWith('/library')) return json({ items: [paper(7, 'Paper Seven'), paper(8, 'Paper Eight')] });
      if (url.endsWith('/projects/1/direction-clusters') && init?.method === 'POST') return json({
        id: 3, project_id: 1, algorithm_version: 'direction-cluster-v1', parameters: { threshold: 0.2 },
        input_hash: 'abc', status: 'succeeded', disclaimer: '这是一种文献组织结果，不是学术领域的客观分类。',
        clusters: [{ id: 4, cluster_key: 'c1', label: 'anomaly detection', terms: ['anomaly', 'detection'], evidence_distribution: { abstract_only: 2 } }],
        members: [
          { paper_id: 7, cluster_id: 4, cluster_key: 'c1', similarity: 0.8, is_unclustered: false },
          { paper_id: 8, cluster_id: 4, cluster_key: 'c1', similarity: 0.7, is_unclustered: false },
        ],
      });
      return json({ detail: `unexpected request: ${url}` }, { status: 500 });
    });
    render(<DirectionMapPage />);
    expect(await screen.findByText(/不是学术领域的客观分类/)).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByLabelText('研究项目'));
    fireEvent.click(await screen.findByText('TSAD'));
    fireEvent.click(await screen.findByLabelText(/Paper Seven/));
    fireEvent.click(screen.getByLabelText(/Paper Eight/));
    fireEvent.click(screen.getByRole('button', { name: '生成方向聚类' }));
    expect(await screen.findByText('anomaly detection')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/algorithm=direction-cluster-v1/)).toBeInTheDocument());
  });
});
