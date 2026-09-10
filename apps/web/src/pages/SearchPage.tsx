import { Alert, Button, Card, Checkbox, Form, Input, List, Pagination, Select, Space, Tag, Typography } from 'antd';
import { Link, useSearchParams } from 'react-router-dom';
import { useEffect, useMemo, useRef, useState } from 'react';
import { apiRequest } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { getApiBaseUrl } from '../lib/runtimeBackend';
import { searchWorkspace, searchTabIdentity, resolveSearchPosition } from '../lib/searchWorkspace';
import { SearchSourceEvidence } from '../components/SearchSourceEvidence';
import type { Paper, SearchSession, SourceStatus } from '../types/domain';

type SearchResponse = { session_id: number; result_count: number; source_status: Record<string, SourceStatus>; search_mode: string; diversity_seed?: string | null; ranking_rule_version: string; composition: Record<string, unknown>; papers: Paper[] };
type SearchValues = { query: string; sources?: string[]; open_access_only?: boolean; mode: 'auto' | 'precise' | 'discovery'; limit: number; adapt_query?: boolean; source_queries?: Record<string, string> };

function compositionText(composition: Record<string, unknown>) {
  const classic = composition.classic_count ?? composition.classic_selected ?? composition.classic_candidates ?? 0;
  const frontier = composition.frontier_count ?? composition.frontier_selected ?? composition.frontier_candidates ?? 0;
  const classicShortfall = composition.classic_shortfall ?? 0;
  const frontierShortfall = composition.frontier_shortfall ?? 0;
  return `经典候选 ${String(classic)} 篇 · 前沿候选 ${String(frontier)} 篇 · 数量缺口 ${String(classicShortfall)} / ${String(frontierShortfall)}`;
}

const modeNames: Record<string, string> = { auto: '自动选择', discovery: '探索相关论文', precise: '精确查找' };
const sourceNames: Record<string, string> = { fixture: '本地示例（非真实检索）', openalex: 'OpenAlex', crossref: 'Crossref', arxiv: 'arXiv', semantic_scholar: 'Semantic Scholar' };

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const { user } = useAuth();
  const environment = getApiBaseUrl();
  const project = Number(params.get('project')) || null;
  const scope = useMemo(() => ({ account: user?.id ?? 0, environment, project, tab: searchTabIdentity }), [user?.id, environment, project]);
    const requestedSession = Number(params.get('session')) || undefined;
    const restored = useMemo(() => searchWorkspace.load(scope, requestedSession), [scope, requestedSession]);
    const expired = useMemo(() => searchWorkspace.loadExpired(scope, requestedSession), [scope, requestedSession, restored]);
  const [selected, setSelected] = useState<number[]>(restored?.selectedIds ?? []);
  const active = useRef<AbortController | null>(null);
  const requestGeneration = useRef(0);
  const [form] = Form.useForm<SearchValues>();
  const [session, setSession] = useState<SearchSession | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [sourceStatus, setSourceStatus] = useState<Record<string, SourceStatus>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [positionNotice, setPositionNotice] = useState<string | null>(null);
  const pendingPosition = useRef<{ paperId?: number; offset?: number; scrollY: number } | null>(null);
  const requestedPage = Number(params.get('page') ?? restored?.page ?? 1);
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const sessionId = Number(params.get('session') ?? restored?.sessionId ?? 0) || null;
  const pageSize = 10;

  useEffect(() => {
    setSession(null); setPapers([]); setSelected([]); setSourceStatus({});
    form.resetFields();
    return () => { active.current?.abort(); };
  }, [scope, form]);

  useEffect(() => {
    if (!sessionId) return;
    active.current?.abort();
    const controller = new AbortController(); active.current = controller;
    const generation = searchWorkspace.beginRequest(); requestGeneration.current = generation;
    setLoading(true); setError(null);
    void Promise.all([
      apiRequest<SearchSession>(`/search/sessions/${sessionId}`, { signal: controller.signal }),
      apiRequest<Paper[]>(`/search/sessions/${sessionId}/papers`, { signal: controller.signal }),
    ]).then(([savedSession, savedPapers]) => {
      if (controller.signal.aborted || !searchWorkspace.isCurrent(generation)) return;
      if ((savedSession.project_id ?? null) !== scope.project) {
        throw new Error('此检索现场不属于当前项目，请在当前项目重新检索。');
      }
      const ordered = savedSession.result_ids.map((id) => savedPapers.find((paper) => paper.id === id)).filter((paper): paper is Paper => Boolean(paper));
      setSession(savedSession); setPapers(ordered); setSourceStatus(savedSession.source_status);
      setSelected(restored?.sessionId === sessionId ? restored.selectedIds.filter((id) => ordered.some((paper) => paper.id === id)) : []);
      form.setFieldsValue({ query: savedSession.query, ...(savedSession.filters as Partial<SearchValues>), mode: savedSession.search_mode as SearchValues['mode'] });
      if (restored?.sessionId === sessionId) {
        const position = resolveSearchPosition(restored, ordered.map((paper) => paper.id), pageSize);
        setPositionNotice(position.notice);
        pendingPosition.current = { ...position.anchor, scrollY: position.notice ? 0 : restored.scrollY };
        setParams((current) => { const next = new URLSearchParams(current); next.set('page', String(position.page)); return next; }, { replace: true });
      }
    }).catch((reason) => { if (!controller.signal.aborted && searchWorkspace.isCurrent(generation)) setError(reason instanceof Error ? reason.message : String(reason)); }).finally(() => { if (!controller.signal.aborted && searchWorkspace.isCurrent(generation)) setLoading(false); });
    return () => controller.abort();
  }, [sessionId, scope, form, restored]);

  useEffect(() => {
    if (loading || !pendingPosition.current) return;
    let frame = 0;
    const restore = () => {
      const position = pendingPosition.current;
      if (!position) return;
      const row = position.paperId ? document.querySelector<HTMLElement>(`[data-search-paper="${position.paperId}"]`) : null;
      if (position.paperId && !row) {
        frame = requestAnimationFrame(restore);
        return;
      }
      window.scrollTo(0, row ? window.scrollY + row.getBoundingClientRect().top - (position.offset ?? 0) : position.scrollY);
      row?.focus({ preventScroll: true });
      pendingPosition.current = null;
    };
    frame = requestAnimationFrame(restore);
    return () => cancelAnimationFrame(frame);
  }, [loading, papers, page]);

  useEffect(() => {
    if (!session || session.id !== sessionId || !user) return;
    const save = () => {
      if (pendingPosition.current) return;
      const visible = [...document.querySelectorAll<HTMLElement>('[data-search-paper]')].find((row) => row.getBoundingClientRect().bottom > 0);
      searchWorkspace.saveIfCurrent(requestGeneration.current, scope, {
      query: session.query, filters: session.filters, sessionId: session.id,
      resultIds: papers.map((paper) => paper.id), selectedIds: selected, page, scrollY: window.scrollY,
      ...(visible ? { anchor: { paperId: Number(visible.dataset.searchPaper), offset: visible.getBoundingClientRect().top } } : {}),
    }); };
    save();
    window.addEventListener('scroll', save, { passive: true });
   return () => { window.removeEventListener('scroll', save); };
  }, [session, sessionId, user, papers, selected, page, scope]);

  const search = async (values: SearchValues) => {
    values = { ...values, source_queries: Object.fromEntries(Object.entries(values.source_queries ?? {}).filter(([, query]) => query?.trim())) };
    active.current?.abort();
    const controller = new AbortController(); active.current = controller;
    const generation = searchWorkspace.beginRequest(); requestGeneration.current = generation;
    setLoading(true); setError(null);
    try {
      const result = await apiRequest<SearchResponse>('/search/papers', { method: 'POST', signal: controller.signal, body: JSON.stringify({ ...values, sources: values.sources ?? [], ...(project ? { project_id: project } : {}) }) });
      if (controller.signal.aborted || !searchWorkspace.isCurrent(generation)) return;
      setSession({ id: result.session_id, project_id: project, query: values.query, filters: values as unknown as Record<string, unknown>, source_status: result.source_status, result_ids: result.papers.map((paper) => paper.id), result_count: result.result_count, search_mode: result.search_mode, diversity_seed: result.diversity_seed, ranking_rule_version: result.ranking_rule_version, composition: result.composition, created_at: new Date().toISOString() });
      setPapers(result.papers); setSourceStatus(result.source_status);
      setSelected([]);
      setParams({ ...(project ? { project: String(project) } : {}), session: String(result.session_id), page: '1' });
    } catch (reason) { if (!controller.signal.aborted && searchWorkspace.isCurrent(generation)) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (!controller.signal.aborted && searchWorkspace.isCurrent(generation)) setLoading(false); }
  };

    const refreshExpiredSearch = () => {
    void form.validateFields().then((values) => {
      searchWorkspace.clearNotice();
      return search(values);
      }).catch(() => undefined);
    };
    const initialValues = useMemo(() => ({
      mode: 'auto' as SearchValues['mode'], limit: 50, adapt_query: true,
      ...(expired ? expired.filters : {}), ...(expired ? { query: expired.query } : {}),
    }), [expired]);

  const pagePapers = useMemo(() => papers.slice((page - 1) * pageSize, page * pageSize), [papers, page]);
  return <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <Card title="找论文" extra={<Typography.Text type="secondary">输入研究问题探索相关论文，或输入题名、DOI 精确查找。</Typography.Text>}>
        <Form form={form} className="search-form" layout="inline" initialValues={initialValues} onFinish={(values) => void search(values)}>
        <Form.Item name="query" rules={[{ required: true, message: '请输入检索内容' }]}><Input placeholder="关键词、题目、DOI、arXiv ID、作者或数据集" /></Form.Item>
        <Form.Item name="mode"><Select style={{ width: 160 }} options={Object.entries(modeNames).map(([value, label]) => ({ value, label }))} /></Form.Item>
        <Form.Item name="limit"><Select style={{ width: 120 }} options={[10, 20, 50].map((value) => ({ value, label: `最多 ${value} 篇` }))} /></Form.Item>
        <Form.Item name="sources"><Select mode="multiple" placeholder="数据源（留空=全部）" style={{ minWidth: 250 }} options={Object.entries(sourceNames).map(([value, label]) => ({ value, label }))} /></Form.Item>
        <Form.Item name="open_access_only" valuePropName="checked"><Checkbox>仅开放全文</Checkbox></Form.Item>
        <Button type="primary" htmlType="submit" loading={loading}>搜索</Button>
        <details style={{ width: '100%' }}>
          <summary>调整各来源检索式（可选）</summary>
          <Typography.Paragraph>保留你的原始问题。留空时使用受控术语表，不认识的术语保留原文；填写后仅覆盖对应的已启用来源，不会额外开启来源。</Typography.Paragraph>
          <Form.Item name="adapt_query" valuePropName="checked"><Checkbox>使用受控术语表适配中英检索</Checkbox></Form.Item>
          {Object.entries(sourceNames).filter(([key]) => key !== 'fixture').map(([key, label]) => <Form.Item key={key} name={['source_queries', key]} label={`${label} 检索式`}><Input maxLength={500} placeholder="留空使用原文或受控适配" /></Form.Item>)}
        </details>
      </Form>
    </Card>
    {error && <Alert type="error" showIcon title="检索失败" description={error} />}
      {searchWorkspace.notice && <Alert type="info" showIcon title="检索现场恢复提示" description={searchWorkspace.notice} action={expired ? <Button onClick={refreshExpiredSearch}>重新确认并搜索</Button> : undefined} />}
    {positionNotice && <Alert type="info" showIcon title="原定位已调整" description={positionNotice} />}
    {session && <Card title={`“${session.query}” · 找到 ${session.result_count} 篇`}>
      <Space wrap><Tag color="blue">{modeNames[session.search_mode] ?? '检索模式待确认'}</Tag><Tag>{compositionText(session.composition)}</Tag></Space>
      <Typography.Paragraph type="secondary" style={{ marginTop: 10 }}>来源返回数量不足时如实保留缺口。检索排序不代表论文已满足你的研究任务；请查看摘要和证据后明确选文。</Typography.Paragraph>
      <Space wrap align="start">{Object.entries(sourceStatus).map(([name, status]) => <SearchSourceEvidence key={name} name={name} status={status} />)}</Space>
    </Card>}
    {papers.length > 0 && <Card title={`结果 · 第 ${page} 页 / 共 ${Math.max(1, Math.ceil(papers.length / pageSize))} 页`} loading={loading}>
      <Typography.Paragraph>已选择 {selected.length} 篇（仅标记选择，不会自动收藏或生成结论）</Typography.Paragraph>
      {selected.length >= 2 && <Link to={`/compare?${new URLSearchParams({ session: String(sessionId), papers: selected.join(','), ...(project ? { project: String(project) } : {}) })}`}>比较所选论文</Link>}
      <List dataSource={pagePapers} renderItem={(paper) => <List.Item tabIndex={-1} data-search-paper={paper.id} actions={[<Link key="detail" to={`/papers/${paper.id}?return=${encodeURIComponent(`/search?session=${session?.id ?? ''}&page=${page}${project ? `&project=${project}` : ''}`)}`}>查看论文与证据</Link>, paper.source_urls[0] ? <a key="source" href={paper.source_urls[0]} target="_blank" rel="noreferrer">原始网页</a> : null]}>
        <List.Item.Meta title={<Space wrap><Checkbox aria-label={`选择 ${paper.title}`} checked={selected.includes(paper.id)} onChange={(event) => setSelected((ids) => event.target.checked ? [...new Set([...ids, paper.id])] : ids.filter((id) => id !== paper.id))} /><Typography.Text strong>{paper.title}</Typography.Text>{paper.ranking && <Tag>{paper.ranking.label === 'classic_candidate' ? '经典候选' : paper.ranking.label === 'frontier_candidate' ? '前沿候选' : '相关性待核验'}</Tag>}{paper.is_fixture && <Tag color="orange">合成示例</Tag>}</Space>} description={<><div>{paper.authors.map((author) => author.name).join(', ') || '作者未知'} · {paper.publication_year ?? '年份未知'} · {paper.venue ?? '发表来源未知'} · 引用数：{paper.citation_count ?? '未知'}</div><Typography.Paragraph ellipsis={{ rows: 3 }}>{paper.abstract ?? '无可访问摘要'}</Typography.Paragraph></>} />
      </List.Item>} />
      <Pagination current={page} total={papers.length} pageSize={pageSize} showSizeChanger={false} onChange={(next) => setParams({ ...(project ? { project: String(project) } : {}), session: String(session?.id ?? ''), page: String(next) })} />
    </Card>}
  </Space>;
}
