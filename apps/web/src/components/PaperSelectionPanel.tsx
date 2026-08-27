import { Alert, Button, Checkbox, Empty, Input, Radio, Select, Space, Spin, Tag, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../api/client';
import type { LibraryItem, Paper, PaperSet, SearchSession } from '../types/domain';

type SourceKind = 'search_session' | 'favorites' | 'manual';

type Props = {
  selected: Paper[];
  onChange: (papers: Paper[]) => void;
  purpose: 'compare' | 'gap';
  ariaLabel: string;
  initialSessionId?: number | null;
  initialPaperSetId?: number | null;
};

type LibraryResponse = { items: LibraryItem[] };
type SearchResponse = { papers: Paper[] };

const sourceOptions = [
  { label: '检索会话', value: 'search_session' },
  { label: '收藏论文', value: 'favorites' },
  { label: '题名检索', value: 'manual' },
];

export function PaperSelectionPanel({ selected, onChange, purpose, ariaLabel, initialSessionId = null, initialPaperSetId = null }: Props) {
  const [sourceKind, setSourceKind] = useState<SourceKind>(initialPaperSetId ? 'favorites' : 'search_session');
  const [sessions, setSessions] = useState<SearchSession[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(initialSessionId);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [manualQuery, setManualQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedIds = useMemo(() => new Set(selected.map((paper) => paper.id)), [selected]);

  const loadSessionPapers = async (id: number) => {
    setLoading(true); setError(null);
    try { setPapers(await apiRequest<Paper[]>(`/search/sessions/${id}/papers`)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    if (initialPaperSetId) {
      setLoading(true);
      void apiRequest<PaperSet>(`/paper-sets/${initialPaperSetId}`)
        .then((paperSet) => { setPapers(paperSet.papers); onChange(paperSet.papers); })
        .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)))
        .finally(() => setLoading(false));
      return;
    }
    if (initialSessionId) {
      setSessionId(initialSessionId);
      void loadSessionPapers(initialSessionId);
      return;
    }
    void apiRequest<SearchSession[]>('/search/sessions').then(setSessions).catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
    // Deliberately do not auto-select sessions[0]. The user must choose a corpus.
  }, [initialPaperSetId, initialSessionId]);

  const switchSource = async (value: string | number) => {
    const next = value as SourceKind;
    setSourceKind(next); setError(null); setPapers([]);
    if (next === 'favorites') {
      setLoading(true);
      try {
        const library = await apiRequest<LibraryResponse>('/library');
        setPapers(library.items.filter((item) => item.favorite).map((item) => item.paper));
      } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
      finally { setLoading(false); }
    } else if (next === 'search_session' && !initialSessionId) {
      try { setSessions(await apiRequest<SearchSession[]>('/search/sessions')); }
      catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    }
  };

  const updateCurrentSource = (ids: number[]) => {
    const visible = new Set(papers.map((paper) => paper.id));
    const preserved = selected.filter((paper) => !visible.has(paper.id));
    const chosen = papers.filter((paper) => ids.includes(paper.id));
    onChange([...preserved, ...chosen]);
  };

  const manualSearch = async () => {
    const query = manualQuery.trim(); if (!query) return;
    setLoading(true); setError(null);
    try {
      const response = await apiRequest<SearchResponse>('/search/papers', { method: 'POST', body: JSON.stringify({ query, mode: 'precise', sources: [], limit: 10 }) });
      setPapers(response.papers);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setLoading(false); }
  };

  return <div className="paper-selection-panel">
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Radio.Group value={sourceKind} options={sourceOptions} optionType="button" buttonStyle="solid" onChange={(event) => void switchSource(event.target.value)} />
      {sourceKind === 'search_session' && !initialSessionId && !initialPaperSetId && <Select
        style={{ width: '100%' }}
        placeholder="明确选择一次检索会话（不会默认使用最近一次）"
        value={sessionId ?? undefined}
        options={sessions.map((session) => ({ value: session.id, label: `${session.query} · ${session.result_count} 篇 · ${session.search_mode}` }))}
        onChange={(value) => { setSessionId(value); void loadSessionPapers(value); }}
        notFoundContent={<><span>没有检索会话。 </span><Link to="/search">先执行论文检索</Link></>}
      />}
      {sourceKind === 'manual' && <Space.Compact style={{ width: '100%' }}><Input value={manualQuery} onChange={(event) => setManualQuery(event.target.value)} onPressEnter={() => void manualSearch()} placeholder="输入明确题名 / DOI / arXiv ID" /><Button onClick={() => void manualSearch()}>检索候选</Button></Space.Compact>}
      {error && <Alert type="error" showIcon title="论文集合载入失败" description={error} />}
      {loading ? <Spin /> : papers.length ? <Checkbox.Group aria-label={ariaLabel} value={[...selectedIds]} onChange={(ids) => updateCurrentSource(ids as number[])}>
        <div className="paper-selection-options">
          {papers.map((paper) => <Checkbox key={paper.id} value={paper.id}>
            <span className="paper-selection-copy"><strong>{paper.title}</strong><span>{paper.publication_year ?? '年份未知'} · {paper.venue ?? 'Venue 未知'}</span><span>{paper.ranking?.label && <Tag>{paper.ranking.label}</Tag>}{paper.is_fixture && <Tag color="orange">FIXTURE</Tag>}</span></span>
          </Checkbox>)}
        </div>
      </Checkbox.Group> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={sourceKind === 'search_session' ? '请选择一个明确检索会话' : sourceKind === 'favorites' ? '暂无收藏论文' : '输入题名后检索'} />}
      <div className="selection-summary"><Typography.Text strong>已选择 {selected.length} 篇</Typography.Text><Typography.Text type="secondary">用于{purpose === 'compare' ? '论文对比' : '候选研究空白'}，生成时会固化为 paper set，不再依赖后续搜索。</Typography.Text>{selected.length > 0 && <div>{selected.map((paper) => <Tag key={paper.id} closable onClose={(event) => { event.preventDefault(); onChange(selected.filter((item) => item.id !== paper.id)); }}>{paper.title}</Tag>)}</div>}</div>
    </Space>
  </div>;
}
