import { Alert, Button, Card, Descriptions, Form, Input, List, Select, Space, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiError, apiRequest } from '../api/client';
import { PaperSelectionPanel } from '../components/PaperSelectionPanel';
import { directEvidenceText, evidenceText, gapState } from '../lib/researchDisplay';
import { citationTarget } from '../lib/citationNavigation';
import type { GapCandidate, Paper, PaperSet, Project } from '../types/domain';

function stringList(values: unknown[]) { return evidenceText(values); }

export function GapsPage() {
  const [params] = useSearchParams();
  const initialPaperSetId = Number(params.get('paperSet') ?? 0) || null;
  const initialSessionId = Number(params.get('session') ?? 0) || null;
  const [projects, setProjects] = useState<Project[]>([]);
  const [gaps, setGaps] = useState<GapCandidate[]>([]);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [projectId, setProjectId] = useState<number | null>(() => {
    const value = Number(params.get('project'));
    return Number.isSafeInteger(value) && value > 0 ? value : null;
  });
  const [challengeTerms, setChallengeTerms] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [scientificDecision, setScientificDecision] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generatingStage, setGeneratingStage] = useState<string | null>(null);
  const fail = (reason: unknown) => setError(reason instanceof Error ? reason.message : '请求未完成，请稍后重试');
  const load = () => { void apiRequest<Project[]>('/projects').then(setProjects).catch(fail); void apiRequest<GapCandidate[]>('/gaps').then(setGaps).catch(fail); };
  useEffect(load, []);

  const generate = async () => {
    if (!projectId || !papers.length) { message.error('请选择研究项目，并显式选择至少一篇论文'); return; }
    setError(null);
    setScientificDecision(false);
    setGenerating(true);
    setGeneratingStage('正在保存本次选文…');
    try {
      const paperSet = await apiRequest<PaperSet>('/paper-sets', { method: 'POST', body: JSON.stringify({ project_id: projectId, purpose: 'gap', name: `候选空白证据集 · ${new Date().toLocaleString()}`, paper_ids: papers.map((paper) => paper.id), source_kind: initialPaperSetId ? 'favorites' : initialSessionId ? 'search_session' : 'explicit' }) });
      setGeneratingStage('正在分析现有论文证据…');
      await apiRequest('/gaps/generate', { method: 'POST', body: JSON.stringify({ project_id: projectId, paper_set_id: paperSet.id }) });
      setGeneratingStage('正在形成可核实的研究问题…');
      message.success('候选研究空白及可解释性分析已生成；当前仍不是创新性证明'); load();
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        setScientificDecision(true);
        return;
      }
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setGenerating(false); setGeneratingStage(null); }
  };
  const challenge = async (gap: GapCandidate) => {
    const additional_terms = (challengeTerms[gap.id] ?? '').split(',').map((term) => term.trim()).filter(Boolean);
    try { await apiRequest(`/gaps/${gap.id}/challenge`, { method: 'POST', body: JSON.stringify({ additional_terms }) }); message.success('检索请求已完成，请检查来源覆盖与待核实材料，再人工审阅'); load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  const confirm = async (gap: GapCandidate) => { try { await apiRequest(`/gaps/${gap.id}/confirm`, { method: 'POST', body: JSON.stringify({ confirmed: true, note: '用户在 ResearchNavigator 界面显式人工确认' }) }); message.success('已记录人工确认'); load(); } catch (reason) { fail(reason); } };
  const createPlan = async (gap: GapCandidate) => { try { await apiRequest('/plans', { method: 'POST', body: JSON.stringify({ project_id: gap.project_id, gap_id: gap.id }) }); message.success('研究计划已创建，可在下一步计划中查看'); } catch (reason) { fail(reason); } };

  return <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <Alert type="warning" showIcon title="候选研究空白是待核实的研究假设，不是创新性证明" description="仅使用你明确选择的论文与方向。相关性未知、论文不相关或关键证据不足时，服务端停止生成。相近研究检索完成后仍需你本人审阅。" />
    {scientificDecision && <Card title="证据判断" data-testid="scientific-decision">
      <Alert type="info" showIcon title="当前证据不足，暂不生成候选研究空白" description="当前证据还不足以确认一个可靠的研究空白。" />
      <Typography.Paragraph>本次比较使用了 {papers.length} 篇你明确选择的论文；这不是研究空白证明，但仍可以保存探索问题并制定验证计划。</Typography.Paragraph>
      <Typography.Paragraph strong>现在可以继续：</Typography.Paragraph>
      <Space wrap>
        <Link to={`/compare${projectId ? `?project=${projectId}` : ''}`}><Button>查看论文差异</Button></Link>
        <Link to={`/search${projectId ? `?project=${projectId}` : ''}`}><Button>补充更多论文</Button></Link>
        <Link to={`/plans${projectId ? `?project=${projectId}&mode=exploration` : ''}`}><Button type="primary">生成验证计划</Button></Link>
      </Space>
    </Card>}
    {error && <Alert type="error" showIcon title="候选研究空白流程失败" description={error} />}
    <Card title="生成候选研究空白"><Form layout="vertical"><Form.Item label="研究项目 / 方向" required><Select placeholder="选择自己的研究方向" value={projectId ?? undefined} options={projects.map((project) => ({ value: project.id, label: `${project.name}${project.broad_direction ? ` · ${project.broad_direction}` : ''}` }))} onChange={setProjectId} /></Form.Item><Form.Item label="证据论文"><PaperSelectionPanel purpose="gap" ariaLabel="选择用于候选研究空白的论文" initialPaperSetId={initialPaperSetId} initialSessionId={initialSessionId} selected={papers} onChange={setPapers} /></Form.Item><Space orientation="vertical" style={{ width: '100%' }}>{generatingStage && <Alert type="info" showIcon message={generatingStage} />}<Button type="primary" loading={generating} disabled={generating || !projectId || !papers.length} onClick={() => void generate()}>构建证据矩阵并解释候选空白</Button></Space></Form></Card>
    <List dataSource={gaps} locale={{ emptyText: '尚未生成候选研究空白' }} renderItem={(gap) => <List.Item><Card style={{ width: '100%' }} title={<Tag>{gap.review_required ? '旧结果需复核' : gapState(gap.status)}</Tag>}>
      {gap.review_required && <Alert type="warning" title={gap.review_reason || '材料或研究方向已变化，请重新核验后继续'} />}
      <Typography.Paragraph strong>{gap.claim}</Typography.Paragraph>
      <Descriptions bordered column={1} size="small"><Descriptions.Item label="研究问题建议">{gap.suggested_research_question}</Descriptions.Item><Descriptions.Item label="作用范围">{gap.scope}</Descriptions.Item><Descriptions.Item label="结论边界">这是待核实问题，不代表领域不存在已有工作</Descriptions.Item><Descriptions.Item label="最小验证">{stringList(gap.minimal_validation)}</Descriptions.Item><Descriptions.Item label="风险因素">{stringList(gap.risk_factors)}</Descriptions.Item></Descriptions>
{gap.explanation && <Card size="small" title="为什么值得继续核实" style={{ marginTop: 16 }}><Descriptions column={1} size="small"><Descriptions.Item label="原文依据">{gap.explanation.direct_evidence.map((entry, index) => <Typography.Paragraph key={index}>{directEvidenceText(entry)} {citationTarget(entry, gap.project_id) && <Link to={citationTarget(entry, gap.project_id)!}>定位原文依据</Link>}</Typography.Paragraph>)}</Descriptions.Item><Descriptions.Item label="系统推断（非原文结论）">{stringList(gap.explanation.inferences)}</Descriptions.Item><Descriptions.Item label="缺失证据">{stringList(gap.explanation.absent_evidence)}</Descriptions.Item><Descriptions.Item label="新颖性风险">{stringList(gap.explanation.novelty_risk_factors)}</Descriptions.Item><Descriptions.Item label="可信范围">{gap.explanation.confidence_rationale}</Descriptions.Item></Descriptions></Card>}
      <Space orientation="vertical" style={{ width: '100%', marginTop: 16 }}><Input value={challengeTerms[gap.id] ?? ''} onChange={(event) => setChallengeTerms((current) => ({ ...current, [gap.id]: event.target.value }))} placeholder="可选：补充相近研究检索词，逗号分隔" /><Space wrap><Button disabled={gap.review_required} onClick={() => void challenge(gap)}>检索相近研究与反证</Button><Button type="primary" disabled={gap.review_required || gap.status !== 'pending_confirmation'} onClick={() => void confirm(gap)}>我已人工审阅并确认</Button><Button disabled={gap.review_required || gap.status !== 'confirmed'} onClick={() => void createPlan(gap)}>创建研究计划</Button></Space></Space>
    </Card></List.Item>} />
  </Space>;
}
