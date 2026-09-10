import type { Paper, PaperAnalysis } from '../types/domain';

const positiveId = (value: unknown) => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;

export function citationTarget(entry: Record<string, unknown>, projectId: number): string | null {
  if (!positiveId(entry.paper_id) || !positiveId(projectId) || typeof entry.supporting_text !== 'string' || !entry.supporting_text.trim() || entry.supporting_text.length > 2000) return null;
  const query = new URLSearchParams({ project: String(projectId), quote: entry.supporting_text });
  if (entry.source_type === 'abstract') query.set('evidenceSource', 'abstract');
  else if (positiveId(entry.chunk_id)) query.set('evidenceChunk', String(entry.chunk_id));
  else return null;
  return `/papers/${entry.paper_id}?${query}`;
}

// URL text is an untrusted locator, never a source of evidence.
export function locateCitation(params: URLSearchParams, paper: Paper | null, analysis: PaperAnalysis | null): string | null {
  const quote = params.get('quote');
  if (!paper || !quote?.trim() || quote.length > 2000) return null;
  if (params.get('evidenceSource') === 'abstract') return paper.abstract_evidence_verified && paper.abstract?.includes(quote) ? quote : null;
  const chunk = Number(params.get('evidenceChunk'));
  if (!positiveId(chunk)) return null;
  const citations = Object.values(analysis?.analysis.field_citations ?? {}).flat();
  return citations.some((citation) => citation.source_type !== 'abstract' && citation.chunk_id === chunk && citation.supporting_text === quote) ? quote : null;
}
