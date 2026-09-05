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
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../api/client';
import { shouldUseDirectUpload, uploadPdfDirect } from '../api/uploads';
import { EvidenceWorkflowPanel } from '../components/EvidenceWorkflowPanel';
import { PaperIntelligenceCards } from '../components/PaperIntelligenceCards';
import { ScoreBreakdown } from '../components/ScoreBreakdown';
import type {
  AuthorCard,
  Citation,
  DatasetCard,
  EvidenceAcquisition,
  EvidenceWorkflow,
  Paper,
  PaperAnalysis,
  PaperAnalysisBody,
  PaperDocument,
  Project,
} from '../types/domain';

type FieldState = 'evidenced' | 'insufficient_evidence' | 'unknown';

function renderValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未在当前可访问文本中找到。';
  if (Array.isArray(value)) return value.length ? value.map(renderValue).join('；') : '未在当前可访问文本中找到。';
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .filter(([, entry]) => entry !== null && entry !== undefined && entry !== '')
      .map(([key, entry]) => `${key}: ${renderValue(entry)}`)
      .join('；') || '未在当前可访问文本中找到。';
  }
  return String(value);
}

function citationLabel(citation: Citation) {
  return [
    citation.source_type,
    citation.section,
    citation.page_start
      ? `p.${citation.page_start}${citation.page_end && citation.page_end !== citation.page_start ? `-${citation.page_end}` : ''}`
      : null,
    citation.chunk_id ? `chunk#${citation.chunk_id}` : null,
  ].filter(Boolean).join(' · ');
}

function EvidenceField({ body, field, label, value }: { body: PaperAnalysisBody; field: string; label: string; value: unknown }) {
  const state = (body.field_states[field] ?? 'unknown') as FieldState;
  const citations = body.field_citations[field] ?? [];
  return <Descriptions.Item label={label}>
    <Space orientation="vertical" size={4} style={{ width: '100%' }}>
      <div>{renderValue(value)}</div>
      <Space wrap>
        <Tag color={state === 'evidenced' ? 'green' : state === 'insufficient_evidence' ? 'orange' : 'default'}>{state}</Tag>
        {citations.map((citation, index) => <Tag key={`${field}-${index}`}>{citationLabel(citation)}</Tag>)}
      </Space>
    </Space>
  </Descriptions.Item>;
}

export function PaperPage() {
  const { paperId } = useParams();
  const [params] = useSearchParams();
  const [paper, setPaper] = useState<Paper | null>(null);
  const [analysis, setAnalysis] = useState<PaperAnalysis | null>(null);
  const [documents, setDocuments] = useState<PaperDocument[]>([]);
  const [authors, setAuthors] = useState<AuthorCard[]>([]);
  const [datasets, setDatasets] = useState<DatasetCard[]>([]);
  const [workflow, setWorkflow] = useState<EvidenceWorkflow | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const [pdf, setPdf] = useState<File | null>(null);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [confirmLimitedLicense, setConfirmLimitedLicense] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acquisitionReport, setAcquisitionReport] = useState<EvidenceAcquisition | null>(null);
  const returnTo = params.get('return');

  const loadPaper = async () => {
    try { setPaper(await apiRequest<Paper>(`/papers/${paperId}`)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  const loadAnalysis = async () => {
    try { setAnalysis(await apiRequest<PaperAnalysis>(`/papers/${paperId}/analysis`)); }
    catch { setAnalysis(null); }
  };
  const loadDocuments = async () => {
    try { setDocuments(await apiRequest<PaperDocument[]>(`/papers/${paperId}/documents`)); }
    catch { setDocuments([]); }
  };
  const loadAuthors = async () => {
    try { setAuthors(await apiRequest<AuthorCard[]>(`/papers/${paperId}/authors`)); }
    catch { setAuthors([]); }
  };
  const loadDatasets = async () => {
    try { setDatasets(await apiRequest<DatasetCard[]>(`/papers/${paperId}/datasets`)); }
    catch { setDatasets([]); }
  };
  const refreshDerived = async () => {
    await Promise.all([loadPaper(), loadAnalysis(), loadDocuments(), loadAuthors(), loadDatasets()]);
  };

  useEffect(() => {
    setError(null);
    void refreshDerived();
    void apiRequest<Project[]>('/projects').then(setProjects).catch(() => setProjects([]));
  }, [paperId]);

  useEffect(() => {
    if (!workflow || workflow.terminal) return;
    const timer = window.setInterval(() => {
      void apiRequest<EvidenceWorkflow>(`/evidence-workflows/${workflow.id}`).then((current) => {
        setWorkflow(current);
        if (current.terminal) void refreshDerived();
      }).catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [workflow?.id, workflow?.terminal]);

  const analyze = async () => {
    setBusy(true); setError(null);
    try {
      const value = await apiRequest<PaperAnalysis>(`/papers/${paperId}/analyze`, {
        method: 'POST',
        body: JSON.stringify({ project_id: projectId, provider: 'configured' }),
      });
      setAnalysis(value);
      await Promise.all([loadDatasets(), loadAuthors()]);
      message.success(value.fallback_reason ? '分析已完成，但 LLM 不可用，已保留确定性结果' : '证据级分析已保存并显示');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const acquireEvidence = async () => {
    setBusy(true); setError(null);
    try {
      const value = await apiRequest<EvidenceAcquisition>(`/papers/${paperId}/acquire-evidence`, {
        method: 'POST',
        body: JSON.stringify({ project_id: projectId, sources: [] }),
      });
      setPaper(value.paper); setAnalysis(value.analysis); setAcquisitionReport(value);
      if (value.outcome === 'abstract_acquired') message.success('已从可审计学术来源补充摘要，并重新执行分析');
      else message.info('已完成摘要证据查询，但未找到可安全合并的新证据');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const createWorkflow = async () => {
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
      setWorkflow(created);
      message.success('证据工作流已创建；pending 只表示已入队，不等于 Worker 已完成');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const runWorkflow = async () => {
    if (!workflow) return;
    setBusy(true); setError(null);
    try {
      const completed = await apiRequest<EvidenceWorkflow>(`/evidence-workflows/${workflow.id}/run`, { method: 'POST' });
      setWorkflow(completed);
      await refreshDerived();
      if (completed.status === 'succeeded') message.success('证据工作流已完成，并自动刷新分析、作者卡与数据集卡');
      else message.warning(`证据工作流以 ${completed.status} 结束；请查看时间线中的来源和失败原因`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const refreshWorkflow = async () => {
    if (!workflow) return;
    setBusy(true); setError(null);
    try {
      const current = await apiRequest<EvidenceWorkflow>(`/evidence-workflows/${workflow.id}`);
      setWorkflow(current);
      if (current.terminal) await refreshDerived();
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const cancelWorkflow = async () => {
    if (!workflow) return;
    setBusy(true); setError(null);
    try {
      const cancelled = await apiRequest<EvidenceWorkflow>(`/evidence-workflows/${workflow.id}/cancel`, { method: 'POST' });
      setWorkflow(cancelled);
      message.info('证据工作流已取消');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const favorite = async () => {
    await apiRequest('/library/favorites', { method: 'POST', body: JSON.stringify({ paper_id: Number(paperId) }) });
    message.success('论文已收藏，可在论文库参与对比、空白探索与方向聚类');
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
      const nextAnalysis = await apiRequest<PaperAnalysis>(`/papers/${paperId}/analyze`, {
        method: 'POST', body: JSON.stringify({ project_id: projectId, provider: 'configured' }),
      });
      setAnalysis(nextAnalysis); setPdf(null); setRightsConfirmed(false);
      await Promise.all([loadDocuments(), loadAuthors(), loadDatasets()]);
      message.success('PDF 已保存，并基于全文重新执行证据级分析');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };
  const removeDocument = async (documentId: number) => {
    setBusy(true);
    try {
      await apiRequest(`/documents/${documentId}`, { method: 'DELETE' });
      await Promise.all([loadDocuments(), loadAnalysis(), loadDatasets()]);
      message.success('PDF、切片和检索索引已删除，证据等级已重新计算');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const evidenceFields = useMemo(() => analysis ? [
    ['executive_summary', '论文总结', analysis.analysis.executive_summary],
    ['research_background', '研究背景', analysis.analysis.research_background],
    ['research_problem', '研究问题', analysis.analysis.research_problem],
    ['task_definition', '任务定义（输入/输出/Setting）', analysis.analysis.task_definition],
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
    ['future_work_explicit', '作者明确 Future Work', analysis.analysis.future_work_explicit],
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

    <Card title={paper.title} extra={paper.is_fixture ? <Tag color="orange">仅演示 Fixture</Tag> : null}>
      <Descriptions column={1} bordered>
        <Descriptions.Item label="作者">{paper.authors.map((author) => author.name).join(', ') || '未知'}</Descriptions.Item>
        <Descriptions.Item label="年份 / Venue">{paper.publication_year ?? '未知'} / {paper.venue ?? '未知'}</Descriptions.Item>
        <Descriptions.Item label="DOI / arXiv">{paper.doi ?? paper.arxiv_id ?? '无'}</Descriptions.Item>
        <Descriptions.Item label="开放状态">{paper.open_access_status ?? '未核验'}</Descriptions.Item>
        <Descriptions.Item label="摘要可信状态">{paper.abstract_evidence_verified ? '已绑定可信来源' : '未验证或不存在'}</Descriptions.Item>
        <Descriptions.Item label="摘要">{paper.abstract ?? '未在当前可访问文本中找到。'}</Descriptions.Item>
      </Descriptions>
      <Divider />
      <Space wrap>
        <Select allowClear placeholder="选择研究项目，用于方向关联分析" style={{ minWidth: 260 }} value={projectId ?? undefined} options={projects.map((project) => ({ value: project.id, label: project.name }))} onChange={(value) => setProjectId(value ?? null)} />
        <Button onClick={() => void favorite()}>收藏论文</Button>
        <Button type="primary" loading={busy} onClick={() => void analyze()}>执行证据级分析</Button>
        {!hasFulltextAnalysis && (analysis?.analysis.evidence_level === 'metadata_only' || paper.is_fixture || paper.abstract_evidence_verified === false) && <Button loading={busy} onClick={() => void acquireEvidence()}>获取更多证据并重新分析</Button>}
        <Button loading={busy} disabled={Boolean(workflow && !workflow.terminal)} onClick={() => void createWorkflow()}>创建完整证据工作流</Button>
        {paper.source_urls[0] && <Button href={paper.source_urls[0]} target="_blank">打开原始网页</Button>}
      </Space>
      <Checkbox style={{ marginTop: 12 }} checked={confirmLimitedLicense} onChange={(event) => setConfirmLimitedLicense(event.target.checked)}>
        对标记为“有限开放许可”的候选全文，我已确认本次研究用途符合其条款；许可证未知时仍只显示入口，不自动摄取。
      </Checkbox>
    </Card>

    <Card title="当前证据状态与缺失提示">
      <Descriptions bordered column={1} size="small">
        <Descriptions.Item label="当前证据等级"><Tag color="blue">{currentEvidenceLevel}</Tag></Descriptions.Item>
        <Descriptions.Item label="摘要来源状态">{paper.abstract_evidence_verified ? '可信摘要已回填' : '需要重新获取可信摘要，或上传/获取合法全文'}</Descriptions.Item>
        <Descriptions.Item label="缺失字段">{missingFields.length ? missingFields.map((field) => <Tag key={field} color="orange">{field}</Tag>) : '无'}</Descriptions.Item>
        <Descriptions.Item label="结论边界">{hasFulltextAnalysis ? '已存在可解析全文，字段仍以实际引用为准。' : '没有可解析全文时，实验协议、作者 Future Work 和正文局限不得由摘要推断。'}</Descriptions.Item>
      </Descriptions>
    </Card>

    {acquisitionReport && <Alert
      type={acquisitionReport.outcome === 'abstract_acquired' ? 'success' : acquisitionReport.outcome === 'source_unavailable' ? 'error' : 'info'}
      showIcon
      title={`摘要证据获取结果：${acquisitionReport.outcome}`}
      description={<Space wrap>{Object.entries(acquisitionReport.source_status).map(([source, status]) => <Tag key={source} color={status.status === 'ok' ? 'green' : status.status === 'error' ? 'red' : 'default'}>{source}: {status.status}{status.detail ? ` · ${status.detail}` : ''}</Tag>)}</Space>}
    />}
    <EvidenceWorkflowPanel workflow={workflow} busy={busy} onRun={() => void runWorkflow()} onCancel={() => void cancelWorkflow()} onRefresh={() => void refreshWorkflow()} />

    <Card title="PDF 全文证据">
      <Alert type="info" showIcon title="全文只在确认具有合法处理权限后摄取" description="自动 OA 获取会先执行许可证判断与安全下载；删除 PDF 时同步删除对应切片和检索索引。" />
      <Space orientation="vertical" style={{ width: '100%', marginTop: 16 }}>
        <input aria-label="合法 PDF 文件" type="file" accept="application/pdf,.pdf" onChange={(event) => setPdf(event.target.files?.[0] ?? null)} />
        <Checkbox checked={rightsConfirmed} onChange={(event) => setRightsConfirmed(event.target.checked)}>我确认有权处理此 PDF</Checkbox>
        <Button disabled={!pdf || !rightsConfirmed} loading={busy} onClick={() => void upload()}>上传并重新分析</Button>
        <List dataSource={documents} locale={{ emptyText: '尚无已上传全文；当前分析将受摘要/元数据证据等级限制。' }} renderItem={(document) => <List.Item actions={[<Button danger key="delete" onClick={() => void removeDocument(document.id)}>删除全文</Button>]}><List.Item.Meta title={document.original_filename} description={`${document.evidence_level} · ${document.page_count} 页 · ${document.chunk_count} chunks · sha256=${document.sha256.slice(0, 12)}…`} /></List.Item>} />
      </Space>
    </Card>

    <PaperIntelligenceCards authors={authors} datasets={datasets} loading={busy} />

    <Card title="个人研究记录"><Space orientation="vertical" style={{ width: '100%' }}><Input.TextArea aria-label="研究笔记" value={note} onChange={(event) => setNote(event.target.value)} /><Button disabled={!note.trim()} onClick={() => void saveNote()}>保存笔记</Button></Space></Card>

    {analysis ? <>
      <Alert type={analysis.analysis.evidence_level === 'abstract_only' ? 'warning' : 'info'} showIcon title={`证据等级：${analysis.analysis.evidence_level}`} description={analysis.analysis.warnings.join('；') || '每个字段都保留当前可访问证据和缺失边界。'} />
      <Card title="分析执行与审计状态">
        <Descriptions bordered column={1} size="small">
          <Descriptions.Item label="analysis_mode">{analysis.analysis_mode ?? 'deterministic'}</Descriptions.Item>
          <Descriptions.Item label="provider / model">{analysis.provider ?? 'deterministic'} / {analysis.model_name ?? '无'}</Descriptions.Item>
          <Descriptions.Item label="prompt_version">{analysis.prompt_version ?? '不适用'}</Descriptions.Item>
          <Descriptions.Item label="fallback_reason">{analysis.fallback_reason ?? '无'}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title="执行证据级分析 · 详细解释">
        <Descriptions bordered column={1}>
          {evidenceFields.map(([field, label, value]) => <EvidenceField key={field} body={analysis.analysis} field={field} label={label} value={value} />)}
          <Descriptions.Item label="缺失字段">{analysis.analysis.missing_fields.length ? analysis.analysis.missing_fields.map((field) => <Tag key={field} color="orange">{field}</Tag>) : '无'}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Row gutter={[16, 16]}><Col xs={24} lg={12}><Card><ScoreBreakdown title="与当前研究方向的匹配度" score={analysis.direction_similarity} /></Card></Col><Col xs={24} lg={12}><Card><ScoreBreakdown title="复现推荐度" score={analysis.reproduction_assessment} /></Card></Col></Row>
    </> : <Alert type="info" showIcon title="尚未执行证据级分析" description="点击“执行证据级分析”后，本页会直接显示方法创新、理论贡献、研究路线、数据集、实验协议、结果、Future Work、局限及字段级引用；状态和缺失提示始终显示在上方。" />}
  </Space>;
}
