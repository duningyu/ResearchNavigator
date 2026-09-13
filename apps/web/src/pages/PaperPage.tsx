import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Descriptions,
  Divider,
  Input,
  List,
  Row,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../api/client';
import { shouldUseDirectUpload, uploadPdfDirect } from '../api/uploads';
import { EvidenceWorkflowPanel } from '../components/EvidenceWorkflowPanel';
import { PaperIntelligenceCards } from '../components/PaperIntelligenceCards';
import { ReadingRecommendationCard } from '../components/ReadingRecommendationCard';
import { ScoreBreakdown } from '../components/ScoreBreakdown';
import { evidenceText, gapState } from '../lib/researchDisplay';
import { locateCitation } from '../lib/citationNavigation';

function translationFailureMessage(reason?: string | null): string {
  if (reason === 'provider_timeout') return '翻译服务响应超时，请稍后重试。';
  if (reason === 'provider_http_429') return '翻译服务当前较忙，请稍后重试。';
  if (reason === 'provider_http_401' || reason === 'provider_http_403') return '翻译服务认证配置异常，请联系维护者。';
  if (reason === 'provider_request_error') return '暂时无法连接翻译服务，请稍后重试。';
  if (reason?.startsWith('provider_http_')) return '翻译服务返回异常，请稍后重试。';
  return '翻译服务暂时不可用，请稍后重试。';
}
import type {
  AuthorCard,
  AbstractTranslation,
  Citation,
  DatasetCard,
  EvidenceAcquisition,
  EvidenceWorkflow,
  Paper,
  PaperAnalysis,
  PaperAnalysisBody,
  PaperDocument,
  Project,
  ReadingRecommendation,
} from '../types/domain';

type FieldState = 'evidenced' | 'insufficient_evidence' | 'unknown';

function citationLabel(citation: Citation) {
  return [
    citation.source_type === 'abstract' ? '摘要原文' : '正文原文',
    citation.section,
    citation.page_start
      ? `p.${citation.page_start}${citation.page_end && citation.page_end !== citation.page_start ? `-${citation.page_end}` : ''}`
      : null,
  ].filter(Boolean).join(' · ');
}

function EvidenceField({ body, field, label, value }: { body: PaperAnalysisBody; field: string; label: string; value: unknown }) {
  const state = (body.field_states[field] ?? 'unknown') as FieldState;
  const citations = body.field_citations[field] ?? [];
  return <section aria-label={label}>
    <Space orientation="vertical" size={4} style={{ width: '100%' }}>
      <div>{evidenceText(value)}</div>
      <Space wrap>
        <Tag color={state === 'evidenced' ? 'green' : state === 'insufficient_evidence' ? 'orange' : 'default'}>{gapState(state)}</Tag>
        {citations.map((citation, index) => <Tag key={`${field}-${index}`}>{citationLabel(citation)}</Tag>)}
      </Space>
      {citations.map((citation, index) => citation.supporting_text ? <blockquote key={index}>{citation.supporting_text}</blockquote> : null)}
    </Space>
  </section>;
}

export function PaperPage() {
  const { paperId } = useParams();
  const [params, setParams] = useSearchParams();
  const [paper, setPaper] = useState<Paper | null>(null);
  const [abstractTranslation, setAbstractTranslation] = useState<AbstractTranslation | null>(null);
  const [translationBusy, setTranslationBusy] = useState(false);
  const [readingRecommendation, setReadingRecommendation] = useState<ReadingRecommendation | null>(null);
  const [abstractView, setAbstractView] = useState<'translated' | 'original'>('translated');
  const [analysis, setAnalysis] = useState<PaperAnalysis | null>(null);
  const [documents, setDocuments] = useState<PaperDocument[]>([]);
  const [authors, setAuthors] = useState<AuthorCard[]>([]);
  const [datasets, setDatasets] = useState<DatasetCard[]>([]);
  const [workflow, setWorkflow] = useState<EvidenceWorkflow | null>(null);
  const [workflowRestored, setWorkflowRestored] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const requestedProject = Number(params.get('project'));
  const projectId = Number.isSafeInteger(requestedProject) && requestedProject > 0 ? requestedProject : null;
  const setProjectId = (value: number | null) => {
    const next = new URLSearchParams(params);
    if (value === null) next.delete('project'); else next.set('project', String(value));
    setParams(next);
  };
  const [note, setNote] = useState('');
  const [pdf, setPdf] = useState<File | null>(null);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [confirmLimitedLicense, setConfirmLimitedLicense] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acquisitionReport, setAcquisitionReport] = useState<EvidenceAcquisition | null>(null);
  const returnTo = params.get('return');
  const citationRegion = useRef<HTMLElement | null>(null);
  const locatedQuote = locateCitation(params, paper, analysis);
  useEffect(() => {
    if (locatedQuote) { citationRegion.current?.scrollIntoView?.({ block: 'center' }); citationRegion.current?.focus(); }
  }, [locatedQuote]);
  const scope = `${paperId}:${projectId ?? ''}`;
  const activeScope = useRef({ key: scope, generation: 0 });
  if (activeScope.current.key !== scope) activeScope.current = { key: scope, generation: activeScope.current.generation + 1 };
  const generation = activeScope.current.generation;
  const isCurrentScope = () => activeScope.current.generation === generation;

  const loadPaper = async () => {
    try { const value = await apiRequest<Paper>(`/papers/${paperId}`); if (isCurrentScope()) setPaper(value); }
    catch (reason) { if (isCurrentScope()) setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  const loadAbstractTranslation = async () => {
    try {
      const value = await apiRequest<AbstractTranslation>(`/papers/${paperId}/abstract-translation?target_language=zh-CN`);
      if (isCurrentScope()) setAbstractTranslation(value);
    } catch {
      if (isCurrentScope()) setAbstractTranslation(null);
    }
  };
  const requestTranslation = async () => {
    if (!paper?.abstract && !abstractTranslation?.original_abstract) return;
    setTranslationBusy(true); setError(null);
    try {
      const value = await apiRequest<AbstractTranslation>(`/papers/${paperId}/abstract-translation?target_language=zh-CN`, { method: 'POST' });
      if (isCurrentScope()) {
        setAbstractTranslation(value);
        if (value.status === 'ready') setAbstractView('translated');
      }
    } catch (reason) {
      if (isCurrentScope()) setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      if (isCurrentScope()) setTranslationBusy(false);
    }
  };
  const loadReadingRecommendation = async () => {
    if (projectId === null) { if (isCurrentScope()) setReadingRecommendation(null); return; }
    try {
      const rows = await apiRequest<Array<{ paper: { id: number }; reading_recommendation: ReadingRecommendation }>>(`/recommendations?project_id=${projectId}`);
      const current = rows.find((row) => row.paper.id === Number(paperId));
      if (isCurrentScope()) setReadingRecommendation(current?.reading_recommendation ?? null);
    } catch { if (isCurrentScope()) setReadingRecommendation(null); }
  };
  const loadAnalysis = async () => {
    try { const value = await apiRequest<PaperAnalysis>(`/papers/${paperId}/analysis${projectId === null ? '' : `?project_id=${projectId}`}`); if (isCurrentScope()) setAnalysis(value); }
    catch { if (isCurrentScope()) setAnalysis(null); }
  };
  const loadDocuments = async () => {
    try { const value = await apiRequest<PaperDocument[]>(`/papers/${paperId}/documents`); if (isCurrentScope()) setDocuments(value); }
    catch { if (isCurrentScope()) setDocuments([]); }
  };
  const loadAuthors = async () => {
    try { const value = await apiRequest<AuthorCard[]>(`/papers/${paperId}/authors`); if (isCurrentScope()) setAuthors(value); }
    catch { if (isCurrentScope()) setAuthors([]); }
  };
  const loadDatasets = async () => {
    try { const value = await apiRequest<DatasetCard[]>(`/papers/${paperId}/datasets`); if (isCurrentScope()) setDatasets(value); }
    catch { if (isCurrentScope()) setDatasets([]); }
  };
  const refreshDerived = async () => {
    await Promise.all([loadPaper(), loadAbstractTranslation(), loadReadingRecommendation(), loadAnalysis(), loadDocuments(), loadAuthors(), loadDatasets()]);
  };

  useEffect(() => {
    setError(null);
    setBusy(false);
    setPaper(null); setAbstractTranslation(null); setReadingRecommendation(null); setAbstractView('translated'); setAnalysis(null); setDocuments([]); setAuthors([]); setDatasets([]);
    setNote(''); setPdf(null); setRightsConfirmed(false); setAcquisitionReport(null);
    void refreshDerived();
    void apiRequest<Project[]>('/projects').then((value) => { if (isCurrentScope()) setProjects(value); }).catch(() => { if (isCurrentScope()) setProjects([]); });
  }, [scope]);

  useEffect(() => {
    let active = true;
    setWorkflow(null);
    setWorkflowRestored(false);
    const query = projectId === null ? '' : `?project_id=${projectId}`;
    void apiRequest<EvidenceWorkflow[]>(`/papers/${paperId}/evidence-workflows${query}`).then((rows) => {
      if (active && isCurrentScope()) {
        setWorkflow(rows.find((row) => row.paper_id === Number(paperId) && row.project_id === projectId) ?? null);
        setWorkflowRestored(true);
      }
    }).catch(() => { if (active && isCurrentScope()) setError('暂时无法恢复材料获取进展，请刷新后再试，避免重复提交。'); });
    return () => { active = false; };
  }, [scope]);

  useEffect(() => {
    if (!workflow || workflow.terminal) return;
    let active = true;
    const timer = window.setInterval(() => {
      void apiRequest<EvidenceWorkflow>(`/evidence-workflows/${workflow.id}`).then((current) => {
        if (!active || !isCurrentScope()) return;
        setWorkflow(current);
        if (current.terminal) void refreshDerived();
      }).catch(() => undefined);
    }, 2500);
    return () => { active = false; window.clearInterval(timer); };
  }, [scope, workflow?.id, workflow?.terminal]);

  const analyze = async () => {
    setBusy(true); setError(null);
    try {
      const value = await apiRequest<PaperAnalysis>(`/papers/${paperId}/analyze`, {
        method: 'POST',
        body: JSON.stringify({ project_id: projectId, provider: 'configured' }),
      });
      if (!isCurrentScope()) return;
      setAnalysis(value);
      await Promise.all([loadDatasets(), loadAuthors()]);
      message.success(value.fallback_reason ? '分析已完成，但 LLM 不可用，已保留确定性结果' : '证据级分析已保存并显示');
    } catch (reason) { if (isCurrentScope()) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (isCurrentScope()) setBusy(false); }
  };

  const acquireEvidence = async () => {
    setBusy(true); setError(null);
    try {
      const value = await apiRequest<EvidenceAcquisition>(`/papers/${paperId}/acquire-evidence`, {
        method: 'POST',
        body: JSON.stringify({ project_id: projectId, sources: [] }),
      });
      if (!isCurrentScope()) return;
      setPaper(value.paper); setAnalysis(value.analysis); setAcquisitionReport(value);
      if (value.outcome === 'abstract_acquired') message.success('已从可审计学术来源补充摘要，并重新执行分析');
      else message.info('已完成摘要证据查询，但未找到可安全合并的新证据');
    } catch (reason) { if (isCurrentScope()) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (isCurrentScope()) setBusy(false); }
  };

  const createWorkflow = async () => {
    if (!workflowRestored || (workflow && !workflow.terminal)) return;
    setBusy(true); setError(null);
    try {
      const created = await apiRequest<EvidenceWorkflow>(`/papers/${paperId}/evidence-workflows`, {
        method: 'POST',
        body: JSON.stringify({
          project_id: projectId,
          sources: [],
          allow_oa_fulltext: true,
          confirm_limited_license: confirmLimitedLicense,
        }),
      });
      if (!isCurrentScope()) return;
      setWorkflow(created);
      const completed = await apiRequest<EvidenceWorkflow>(`/evidence-workflows/${created.id}/run`, { method: 'POST' });
      if (!isCurrentScope()) return;
      setWorkflow(completed);
      await refreshDerived();
      message.info(`材料处理：${gapState(completed.status)}，请核对实际可用材料`);
    } catch (reason) { if (isCurrentScope()) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (isCurrentScope()) setBusy(false); }
  };

  const runWorkflow = async () => {
    if (!workflow) return;
    setBusy(true); setError(null);
    try {
      const completed = await apiRequest<EvidenceWorkflow>(`/evidence-workflows/${workflow.id}/run`, { method: 'POST' });
      if (!isCurrentScope()) return;
      setWorkflow(completed);
      await refreshDerived();
      if (completed.status === 'succeeded' && completed.result_integrity === 'verified') message.success('证据工作流已完成，并自动刷新分析、作者卡与数据集卡');
      else message.warning(`材料处理：${gapState(completed.status)}，请核对来源状态`);
    } catch (reason) { if (isCurrentScope()) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (isCurrentScope()) setBusy(false); }
  };

  const refreshWorkflow = async () => {
    if (!workflow) return;
    setBusy(true); setError(null);
    try {
      const current = await apiRequest<EvidenceWorkflow>(`/evidence-workflows/${workflow.id}`);
      if (!isCurrentScope()) return;
      setWorkflow(current);
      if (current.terminal) await refreshDerived();
    } catch (reason) { if (isCurrentScope()) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (isCurrentScope()) setBusy(false); }
  };

  const cancelWorkflow = async () => {
    if (!workflow) return;
    setBusy(true); setError(null);
    try {
      const cancelled = await apiRequest<EvidenceWorkflow>(`/evidence-workflows/${workflow.id}/cancel`, { method: 'POST' });
      if (!isCurrentScope()) return;
      setWorkflow(cancelled);
      message.info('证据工作流已取消');
    } catch (reason) { if (isCurrentScope()) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (isCurrentScope()) setBusy(false); }
  };

  const favorite = async () => {
    await apiRequest('/library/favorites', { method: 'POST', body: JSON.stringify({ paper_id: Number(paperId) }) });
    message.success('已保存到我的论文，可明确选文后比较并核实研究机会');
  };
  const saveNote = async () => {
    await apiRequest('/library/notes', { method: 'POST', body: JSON.stringify({ paper_id: Number(paperId), content: note }) });
    setNote(''); message.success('笔记已保存');
  };
  const upload = async () => {
    if (!pdf || !rightsConfirmed) return;
    setBusy(true); setError(null);
    try {
      if (shouldUseDirectUpload()) {
        await uploadPdfDirect(paperId ?? '', pdf);
      } else {
        const body = new FormData(); body.append('file', pdf); body.append('rights_confirmed', 'true');
        await apiRequest(`/papers/${paperId}/upload`, { method: 'POST', body });
      }
      if (!isCurrentScope()) return;
      const nextAnalysis = await apiRequest<PaperAnalysis>(`/papers/${paperId}/analyze`, {
        method: 'POST', body: JSON.stringify({ project_id: projectId, provider: 'configured' }),
      });
      if (!isCurrentScope()) return;
      setAnalysis(nextAnalysis); setPdf(null); setRightsConfirmed(false);
      await Promise.all([loadDocuments(), loadAuthors(), loadDatasets()]);
      message.success('PDF 已保存，分析以实际提取到的文本为准；请核对材料覆盖范围');
    } catch (reason) { if (isCurrentScope()) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (isCurrentScope()) setBusy(false); }
  };
  const removeDocument = async (documentId: number) => {
    setBusy(true);
    try {
      await apiRequest(`/documents/${documentId}`, { method: 'DELETE' });
      if (!isCurrentScope()) return;
      await Promise.all([loadDocuments(), loadAnalysis(), loadDatasets()]);
      message.success('PDF、切片和检索索引已删除，证据等级已重新计算');
    } catch (reason) { if (isCurrentScope()) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (isCurrentScope()) setBusy(false); }
  };

  const evidenceFields = useMemo(() => analysis ? [
    ['executive_summary', '快速解读', analysis.analysis.executive_summary],
    ['research_background', '研究背景', analysis.analysis.research_background],
    ['research_problem', '研究问题', analysis.analysis.research_problem],
    ['task_definition', '任务定义（输入、输出与研究条件）', analysis.analysis.task_definition],
    ['theoretical_contribution', '理论创新 / 理论贡献', analysis.analysis.theoretical_contribution],
    ['method_innovation', '方法创新', analysis.analysis.method_innovation],
    ['research_route', '研究路线', analysis.analysis.research_route],
    ['inputs', '输入', analysis.analysis.inputs],
    ['outputs', '输出', analysis.analysis.outputs],
    ['core_methods', '核心方法', analysis.analysis.core_methods],
    ['new_modules', '新增模块 / 结构', analysis.analysis.new_modules],
    ['datasets', '数据集', analysis.analysis.datasets],
    ['baselines', '对比基线', analysis.analysis.baselines],
    ['metrics', '评测指标', analysis.analysis.metrics],
    ['experimental_protocol', '实验协议 / 切分', analysis.analysis.experimental_protocol],
    ['major_results', '主要结果', analysis.analysis.major_results],
    ['claimed_contributions', '作者声明贡献', analysis.analysis.claimed_contributions],
    ['future_work_explicit', '作者明确提出的后续研究', analysis.analysis.future_work_explicit],
    ['limitations_author_stated', '作者明确局限', analysis.analysis.limitations_author_stated],
    ['limitations_inferred', '系统推断局限（非作者声明）', analysis.analysis.limitations_inferred],
  ] as Array<[string, string, unknown]> : [], [analysis]);
  const hasFulltextAnalysis = analysis ? ['open_fulltext', 'user_uploaded_fulltext', 'publisher_authorized_fulltext'].includes(analysis.analysis.evidence_level) : false;
  const currentEvidenceLevel = workflow?.strongest_evidence
    ?? analysis?.analysis.evidence_level
    ?? (paper?.abstract_evidence_verified ? 'abstract_only' : 'metadata_only');
  const missingFields = analysis?.analysis.missing_fields ?? ['analysis_not_run'];

  if (!paper && !error) return <Card loading />;
  if (!paper) return <Alert type="error" showIcon title="论文载入失败" description={error} />;

  return <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    {returnTo && <div><Link to={returnTo}>← 返回原检索页与页码</Link></div>}
    {error && <Alert type="error" showIcon title="操作失败" description={error} />}
    {params.has('quote') && (locatedQuote
      ? <section ref={citationRegion} tabIndex={-1} aria-label="已定位的原文依据"><Card title="已定位的原文依据"><blockquote>{locatedQuote}</blockquote><Typography.Text>已与当前论文材料匹配；原文保留，不将引用内容视为系统指令。</Typography.Text></Card></section>
      : <Alert type="warning" title="未找到对应原文片段，材料可能已更新；请重新核对引用。" />)}

    <Card title={paper.title} extra={paper.is_fixture ? <Tag color="orange">仅演示 Fixture</Tag> : null}>
      <Descriptions column={1} bordered>
        <Descriptions.Item label="作者">{paper.authors.map((author) => author.name).join(', ') || '未知'}</Descriptions.Item>
        <Descriptions.Item label="年份 / Venue">{paper.publication_year ?? '未知'} / {paper.venue ?? '未知'}</Descriptions.Item>
        <Descriptions.Item label="DOI / arXiv">{paper.doi ?? paper.arxiv_id ?? '无'}</Descriptions.Item>
        <Descriptions.Item label="开放状态">{paper.open_access_status ?? '未核验'}</Descriptions.Item>
        <Descriptions.Item label="摘要可信状态">{paper.abstract_evidence_verified ? '已绑定可信来源' : '未验证或不存在'}</Descriptions.Item>
        <Descriptions.Item label="摘要译文">
          <Space orientation="vertical" style={{ width: '100%' }}>
            {abstractTranslation?.status === 'ready' && abstractView === 'translated'
              ? abstractTranslation.translated_abstract
              : abstractTranslation?.original_abstract ?? paper.abstract ?? '当前来源未提供摘要。'}
            {abstractTranslation?.status === 'ready' && abstractView === 'translated' && <Typography.Text type="secondary">中文译文由当前原始摘要生成，专名、数字和单位按原文保留。</Typography.Text>}
            {abstractTranslation?.status === 'unavailable' && <Alert type="warning" showIcon message="中文译文暂未生成，以下为论文原始摘要。" />}
            {abstractTranslation?.status === 'failed' && <Alert type="warning" showIcon title={translationFailureMessage(abstractTranslation.fallback_reason)} description="以下仍显示论文原始摘要，不影响继续阅读。" />}
            {abstractTranslation?.status === 'partial' && <Alert type="warning" showIcon message="译文不完整，以下为论文原始摘要。" />}
            <Space wrap>
              <Button size="small" disabled={!abstractTranslation?.original_abstract && !paper.abstract} onClick={() => setAbstractView('original')}>查看原文</Button>
              <Button size="small" disabled={abstractTranslation?.status !== 'ready'} onClick={() => setAbstractView('translated')}>查看中文</Button>
              {(paper.abstract || abstractTranslation?.original_abstract) && abstractTranslation?.status !== 'ready' && <Button size="small" loading={translationBusy} onClick={() => void requestTranslation()}>{translationBusy ? '正在翻译摘要…' : abstractTranslation?.status === 'failed' || abstractTranslation?.status === 'partial' ? '重新翻译' : '生成中文译文'}</Button>}
            </Space>
          </Space>
        </Descriptions.Item>
      </Descriptions>
      <Divider />
      <Space wrap>
        <Select allowClear placeholder="选择研究课题，用于方向关联分析" style={{ minWidth: 260 }} value={projectId ?? undefined} options={projects.map((project) => ({ value: project.id, label: project.name }))} onChange={(value) => setProjectId(value ?? null)} />
        <Button onClick={() => void favorite()}>收藏论文</Button>
        <Button type="primary" loading={busy} onClick={() => void analyze()}>执行证据级分析</Button>
        {!hasFulltextAnalysis && (analysis?.analysis.evidence_level === 'metadata_only' || paper.is_fixture || paper.abstract_evidence_verified === false) && <Button loading={busy} onClick={() => void acquireEvidence()}>获取更多证据并重新分析</Button>}
        <Button loading={busy} disabled={!workflowRestored || Boolean(workflow && !workflow.terminal)} onClick={() => void createWorkflow()}>获取公开材料并分析</Button>
        {paper.source_urls[0] && <Button href={paper.source_urls[0]} target="_blank">打开原始网页</Button>}
      </Space>
      <Checkbox style={{ marginTop: 12 }} checked={confirmLimitedLicense} onChange={(event) => setConfirmLimitedLicense(event.target.checked)}>
        对标记为“有限开放许可”的候选全文，我已确认本次研究用途符合其条款；许可证未知时仍只显示入口，不自动摄取。
      </Checkbox>
    </Card>

    <Card title="当前证据状态与缺失提示">
      <Descriptions bordered column={1} size="small">
        <Descriptions.Item label="当前证据等级"><Tag color="blue">{gapState(currentEvidenceLevel)}</Tag></Descriptions.Item>
        <Descriptions.Item label="摘要来源状态">{paper.abstract_evidence_verified ? '可信摘要已回填' : '需要重新获取可信摘要，或上传/获取合法全文'}</Descriptions.Item>
        <Descriptions.Item label="待补充材料">{missingFields.length ? `${missingFields.length} 项信息仍待核实，请查看下方逐项依据。` : '已提取字段仍需核对原文，不代表研究问题已解决。'}</Descriptions.Item>
        <Descriptions.Item label="结论边界">{hasFulltextAnalysis ? '已提取正文片段，不代表完整正文；字段以实际引用为准。' : '当前主要依据摘要或书目信息，不能据此推断正文未披露的实验细节。'}</Descriptions.Item>
      </Descriptions>
    </Card>

    {readingRecommendation && <ReadingRecommendationCard recommendation={readingRecommendation} />}

    {acquisitionReport && <Alert
      type={acquisitionReport.outcome === 'abstract_acquired' ? 'success' : acquisitionReport.outcome === 'source_unavailable' ? 'error' : 'info'}
      showIcon
      title={`摘要获取结果：${gapState(acquisitionReport.outcome)}`}
      description={<Space wrap>{Object.entries(acquisitionReport.source_status).map(([source, status]) => <Tag key={source}>{source}: {gapState(status.status)}</Tag>)}</Space>}
    />}
    <EvidenceWorkflowPanel workflow={workflow} busy={busy} onRun={() => void runWorkflow()} onCancel={() => void cancelWorkflow()} onRefresh={() => void refreshWorkflow()} />

    <Card title="PDF 全文证据">
      <Alert type="info" showIcon title="全文只在确认具有合法处理权限后摄取" description="自动 OA 获取会先执行许可证判断与安全下载；删除 PDF 时同步删除对应切片和检索索引。" />
      <Space orientation="vertical" style={{ width: '100%', marginTop: 16 }}>
        <input aria-label="合法 PDF 文件" type="file" accept="application/pdf,.pdf" onChange={(event) => setPdf(event.target.files?.[0] ?? null)} />
        <Checkbox checked={rightsConfirmed} onChange={(event) => setRightsConfirmed(event.target.checked)}>我确认有权处理此 PDF</Checkbox>
        <Button disabled={!pdf || !rightsConfirmed} loading={busy} onClick={() => void upload()}>上传并重新分析</Button>
        <List dataSource={documents} locale={{ emptyText: '尚无已获取正文；先阅读可信摘要，不将获取失败等同于收费。' }} renderItem={(document) => <List.Item actions={[<Button danger key="delete" onClick={() => void removeDocument(document.id)}>删除全文</Button>]}><List.Item.Meta title={document.original_filename} description={`${gapState(document.evidence_level)} · ${document.page_count} 页 · 已提取 ${document.chunk_count} 段；完整性尚需核对`} /></List.Item>} />
      </Space>
    </Card>

    <PaperIntelligenceCards authors={authors} datasets={datasets} loading={busy} />

    <Card title="个人研究记录"><Space orientation="vertical" style={{ width: '100%' }}><Input.TextArea aria-label="研究笔记" value={note} onChange={(event) => setNote(event.target.value)} /><Button disabled={!note.trim()} onClick={() => void saveNote()}>保存笔记</Button></Space></Card>

    {analysis ? <>
      <Alert type={analysis.analysis.evidence_level === 'abstract_only' ? 'warning' : 'info'} showIcon title={`现有材料：${gapState(analysis.analysis.evidence_level)}`} description={analysis.fallback_reason ? '模型分析不可用，当前保留规则抽取的材料，不代表模型推理已完成。' : '每项结论以可定位的原文为准，缺失信息不作推断。'} />
      <Card title="执行证据级分析 · 详细解释">
        <Alert type="info" showIcon description="证据缺失会降低分析置信度，但与当前课题的初步匹配判断可基于标题、摘要和研究方向进行；复现准备情况只依据已经核验的信息。" />
        <Descriptions bordered column={1}>
          {evidenceFields.map(([field, label, value]) => <Descriptions.Item key={field} label={label}><EvidenceField body={analysis.analysis} field={field} label={label} value={value} /></Descriptions.Item>)}
        </Descriptions>
      </Card>
      <Row gutter={[16, 16]}><Col xs={24} lg={12}><Card><ScoreBreakdown title="与当前研究课题的匹配度" score={analysis.direction_similarity} /></Card></Col><Col xs={24} lg={12}><Card><ScoreBreakdown title="复现准备情况" score={analysis.reproduction_assessment} /></Card></Col></Row>
    </> : <Alert type="info" showIcon title="尚未执行证据级分析" description="点击“执行证据级分析”后，本页会直接显示方法创新、理论贡献、研究路线、数据集、实验协议、结果、Future Work、局限及字段级引用；状态和缺失提示始终显示在上方。" />}
  </Space>;
}
