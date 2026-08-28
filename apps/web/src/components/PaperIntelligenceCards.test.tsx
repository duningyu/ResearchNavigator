import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { PaperIntelligenceCards } from './PaperIntelligenceCards';

afterEach(cleanup);

describe('PaperIntelligenceCards', () => {
  it('renders provenance-aware author and dataset cards without inventing missing values', () => {
    render(<PaperIntelligenceCards authors={[{
      id: 1, canonical_name: 'A. Researcher', orcid: null, openalex_id: 'A1', semantic_scholar_id: null,
      affiliations: [], topics: ['time-series'], works_count: null, citation_count: null, homepage: null,
      identity_status: 'resolved_identifier', provenance: [{ source: 'openalex' }], position: 1, credit_roles: [],
    }]} datasets={[{
      id: 2, canonical_name: 'SWaT', access_url: null, license: null, domain: 'industrial time-series',
      identity_status: 'mentioned_only', provenance: [], mention_id: 3, paper_id: 7, analysis_id: 8,
      raw_mention: 'SWaT', role: 'evaluation', task: null, train_split: null, validation_split: null,
      test_split: null, metrics: [], evidence_level: 'abstract_only', field_citations: {},
    }]} loading={false} />);
    expect(screen.getByText('A. Researcher')).toBeInTheDocument();
    expect(screen.getByText('resolved_identifier')).toBeInTheDocument();
    const rawMentionRow = screen.getByText('原文提及').closest('tr');
    expect(rawMentionRow).not.toBeNull();
    expect(within(rawMentionRow as HTMLElement).getByText('SWaT')).toBeInTheDocument();
    expect(screen.getByText('mentioned_only')).toBeInTheDocument();
    expect(screen.getAllByText('未在当前可访问证据中找到。').length).toBeGreaterThan(0);
  });
});
