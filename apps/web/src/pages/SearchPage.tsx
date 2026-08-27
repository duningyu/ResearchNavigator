import { Alert, Button, Card, Checkbox, Form, Input, List, Pagination, Select, Space, Tag, Typography } from 'antd';
import { Link, useSearchParams } from 'react-router-dom';
import { useEffect, useMemo, useState } from 'react';
import { apiRequest } from '../api/client';
import type { Paper, SearchSession, SourceStatus } from '../types/domain';

type SearchResponse = { session_id: number; result_count: number; source_status: Record<string, SourceStatus>; search_mode: string; diversity_seed?: string | null; ranking_rule_version: string; composition: Record<string, unknown>; papers: Paper[] };
type SearchValues = { query: string; sources?: string[]; open_access_only?: boolean; mode: 'auto' | 'precise' | 'discovery'; limit: number };

function compositionText(composition: Record<string, unknown>) {
  const classic = composition.classic_count ?? composition.classic_selected ?? composition.classic_candidates ?? 0;
  const frontier = composition.frontier_count ?? composition.frontier_selected ?? composition.frontier_candidates ?? 0;
  const classicShortfall = composition.classic_shortfall ?? 0;
  const frontierShortfall = composition.frontier_shortfall ?? 0;
  return `classic=${String(classic)} · frontier=${String(frontier)} · shortfall=${String(classicShortfall)}/${String(frontierShortfall)}`;
}

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const [form] = Form.useForm<SearchValues>();
  const [session, setSession] = useState<SearchSession | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [sourceStatus, setSourceStatus] = useState<Record<string, SourceStatus>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const page = Math.max(1, Number(params.get('page') ?? 1));
  const sessionId = Number(params.get('session') ?? 0) || null;
  const pageSize = 10;

  useEffect(() => {
    if (!sessionId) return;
    setLoading(true); setError(null);
    void Promise.all([
      apiRequest<SearchSession>(`/search/sessions/${sessionId}`),
      apiRequest<Paper[]>(`/search/sessions/${sessionId}/papers`),
    ]).then(([savedSession, savedPapers]) => {
      setSession(savedSession); setPapers(savedPapers); setSourceStatus(savedSession.source_status);
      form.setFieldsValue({ query: savedSession.query, ...(savedSession.filters as Partial<SearchValues>), mode: savedSession.search_mode as SearchValues['mode'] });
    }).catch((reason) => setError(reason instanceof Error ? reason.message : String(reason))).finally(() => setLoading(false));
  }, [sessionId]);

  const search = async (values: SearchValues) => {
    setLoading(true); setError(null);
    try {
      const result = await apiRequest<SearchResponse>('/search/papers', { method: 'POST', body: JSON.stringify({ ...values, sources: values.sources ?? [] }) });
      setSession({ id: result.session_id, project_id: null, query: values.query, filters: values as unknown as Record<string, unknown>, source_status: result.source_status, result_ids: result.papers.map((paper) => paper.id), result_count: result.result_count, search_mode: result.search_mode, diversity_seed: result.diversity_seed, ranking_rule_version: result.ranking_rule_version, composition: result.composition, created_at: new Date().toISOString() });
      setPapers(result.papers); setSourceStatus(result.source_status);
      setParams({ session: String(result.session_id), page: '1' });
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setLoading(false); }
  };

  const pagePapers = useMemo(() => papers.slice((page - 1) * pageSize, page * pageSize), [papers, page]);
  return <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <Card title="多源论文检索" extra={<Typography.Text type="secondary">模糊概念词自动进入 Discovery；明确题名/DOI 使用 Precise。</Typography.Text>}>
      <Form form={form} className="search-form" layout="inline" initialValues={{ mode: 'auto', limit: 50 }} onFinish={(values) => void search(values)}>
        <Form.Item name="query" rules={[{ required: true, message: '请输入检索内容' }]}><Input placeholder="关键词、题目、DOI、arXiv ID、作者或数据集" /></Form.Item>
        <Form.Item name="mode"><Select style={{ width: 140 }} options={[{ value: 'auto', label: 'Auto' }, { value: 'discovery', label: 'Discovery' }, { value: 'precise', label: 'Precise' }]} /></Form.Item>
        <Form.Item name="limit"><Select style={{ width: 120 }} options={[10, 20, 50].map((value) => ({ value, label: `Top ${value}` }))} /></Form.Item>
        <Form.Item name="sources"><Select mode="multiple" placeholder="数据源（留空=全部）" style={{ minWidth: 250 }} options={['fixture','openalex','crossref','arxiv','semantic_scholar'].map((value) => ({ value }))} /></Form.Item>
        <Form.Item name="open_access_only" valuePropName="checked"><Checkbox>仅开放全文</Checkbox></Form.Item>
        <Button type="primary" htmlType="submit" loading={loading}>搜索</Button>
      </Form>
    </Card>
    {error && <Alert type="error" showIcon title="检索失败" description={error} />}
    {session && <Card title={`检索会话 #${session.id} · ${session.result_count} 篇`}>
      <Space wrap><Tag color="blue">mode={session.search_mode}</Tag><Tag>rule={session.ranking_rule_version}</Tag>{session.diversity_seed && <Tag>seed={session.diversity_seed.slice(0, 12)}…</Tag>}<Tag>{compositionText(session.composition)}</Tag></Space>
      <Typography.Paragraph type="secondary" style={{ marginTop: 10 }}>Discovery Top50 以 10 篇经典候选 + 40 篇前沿候选为目标；真实来源不足时显示 shortfall，不伪造论文。顺序和 seed 固化在该 search session 中。</Typography.Paragraph>
      <Space wrap>{Object.entries(sourceStatus).map(([name, status]) => <Tag color={status.status === 'ok' ? 'green' : status.status === 'error' ? 'red' : 'default'} key={name}>{name}: {status.status}</Tag>)}</Space>
    </Card>}
    {papers.length > 0 && <Card title={`结果 · 第 ${page} 页 / 共 ${Math.max(1, Math.ceil(papers.length / pageSize))} 页`} loading={loading}>
      <List dataSource={pagePapers} renderItem={(paper) => <List.Item actions={[<Link key="detail" to={`/papers/${paper.id}?return=${encodeURIComponent(`/search?session=${session?.id ?? ''}&page=${page}`)}`}>证据级分析</Link>, paper.source_urls[0] ? <a key="source" href={paper.source_urls[0]} target="_blank" rel="noreferrer">原始网页</a> : null]}>
        <List.Item.Meta title={<Space wrap><Typography.Text strong>{paper.title}</Typography.Text>{paper.ranking && <Tag color={paper.ranking.label === 'classic_candidate' ? 'gold' : paper.ranking.label === 'frontier_candidate' ? 'cyan' : 'default'}>{paper.ranking.label}</Tag>}{paper.ranking && <Tag>#{paper.ranking.position}</Tag>}{paper.is_fixture && <Tag color="orange">FIXTURE</Tag>}</Space>} description={<><div>{paper.authors.map((author) => author.name).join(', ') || '作者未知'} · {paper.publication_year ?? '年份未知'} · {paper.venue ?? 'Venue 未知'} · citations={paper.citation_count ?? '未知'}</div><Typography.Paragraph ellipsis={{ rows: 3 }}>{paper.abstract ?? '无可访问摘要'}</Typography.Paragraph></>} />
      </List.Item>} />
      <Pagination current={page} total={papers.length} pageSize={pageSize} showSizeChanger={false} onChange={(next) => setParams({ session: String(session?.id ?? ''), page: String(next) })} />
    </Card>}
  </Space>;
}
