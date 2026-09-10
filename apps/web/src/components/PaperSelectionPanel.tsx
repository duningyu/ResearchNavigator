import { Alert, Button, Checkbox, Empty, Input, Radio, Select, Space, Spin, Tag, Typography } from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';
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
  initialSelectedIds?: number[];
};

type LibraryResponse = { items: LibraryItem[] };
type SearchResponse = { papers: Paper[] };

const sourceOptions = [
  { label: '检索会话', value: 'search_session' },
  { label: '收藏论文', value: 'favorites' },
  { label: '题名检索', value: 'manual' },
];

export function PaperSelectionPanel({ selected, onChange, purpose, ariaLabel, initialSessionId = null, initialPaperSetId = null, initialSelectedIds }: Props) {
  const [sourceKind, setSourceKind] = useState<SourceKind>(initialPaperSetId ? 'favorites' : 'search_session');
  const [sessions, setSessions] = useState<SearchSession[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(initialSessionId);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [manualQuery, setManualQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestVersion = useRef(0);

  const selectedIds = useMemo(() => new Set(selected.map((paper) => paper.id)), [selected]);

  const loadSessionPapers = async (id: number, explicitIds?: number[]) => {
    const version = ++requestVersion.current;
    setLoading(true); setError(null);
    try {
      const loaded = await apiRequest<Paper[]>(`/search/sessions/${id}/papers`);
      if (version !== requestVersion.current) return;
      setPapers(loaded);
      if (explicitIds) onChange(loaded.filter((paper) => explicitIds.includes(paper.id)));
    }
    catch (reason) { if (version === requestVersion.current) setError(reason instanceof Error ? reason.message : '论文载入失败'); }
    finally { if (version === requestVersion.current) setLoading(false); }
  };

  useEffect(() => {
    const version = ++requestVersion.current;
    const dispose = () => { ++requestVersion.current; };
    if (initialPaperSetId) {
      setLoading(true);
      void apiRequest<PaperSet>(`/paper-sets/${initialPaperSetId}`)
        .then((paperSet) => { if (version === requestVersion.current) { setPapers(paperSet.papers); onChange(paperSet.papers); } })
        .catch((reason) => { if (version === requestVersion.current) setError(reason instanceof Error ? reason.message : '论文集合载入失败'); })
        .finally(() => { if (version === requestVersion.current) setLoading(false); });
      return dispose;
    }
    if (initialSessionId) {
      setSessionId(initialSessionId);
      void loadSessionPapers(initialSessionId, initialSelectedIds);
      return dispose;
    }
    void apiRequest<SearchSession[]>('/search/sessions')
      .then((rows) => { if (version === requestVersion.current) setSessions(rows); })
      .catch((reason) => { if (version === requestVersion.current) setError(reason instanceof Error ? reason.message : '检索记录载入失败'); });
    // Deliberately do not auto-select sessions[0]. The user must choose a corpus.
    return dispose;
  }, [initialPaperSetId, initialSessionId]);

  const switchSource = async (value: string | number) => {
    const version = ++requestVersion.current;
    const next = value as SourceKind;
    setSourceKind(next); setError(null); setPapers([]); setLoading(false);
    if (next === 'favorites') {
      setLoading(true);
      try {
        const library = await apiRequest<LibraryResponse>('/library');
        if (version === requestVersion.current) setPapers(library.items.filter((item) => item.favorite).map((item) => item.paper));
      } catch (reason) { if (version === requestVersion.current) setError(reason instanceof Error ? reason.message : '收藏载入失败'); }
      finally { if (version === requestVersion.current) setLoading(false); }
    } else if (next === 'search_session' && !initialSessionId) {
      try { const rows = await apiRequest<SearchSession[]>('/search/sessions'); if (version === requestVersion.current) setSessions(rows); }
      catch (reason) { if (version === requestVersion.current) setError(reason instanceof Error ? reason.message : '检索记录载入失败'); }
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
    const version = ++requestVersion.current;
    setLoading(true); setError(null);
    try {
      const response = await apiRequest<SearchResponse>('/search/papers', { method: 'POST', body: JSON.stringify({ query, mode: 'precise', sources: [], limit: 10 }) });
      if (version === requestVersion.current) setPapers(response.papers);
    } catch (reason) { if (version === requestVersion.current) setError(reason instanceof Error ? reason.message : '论文检索失败'); }
    finally { if (version === requestVersion.current) setLoading(false); }
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
