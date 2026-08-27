import { Alert, Button, Card, Descriptions, Form, Input, List, Select, Space, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiRequest } from '../api/client';
import { PaperSelectionPanel } from '../components/PaperSelectionPanel';
import type { GapCandidate, Paper, PaperSet, Project } from '../types/domain';

function stringList(values: unknown[]) { return values.length ? values.map((value) => typeof value === 'string' ? value : JSON.stringify(value)).join('；') : '无 / 当前证据不足'; }

export function GapsPage() {
  const [params] = useSearchParams();
  const initialPaperSetId = Number(params.get('paperSet') ?? 0) || null;
  const initialSessionId = Number(params.get('session') ?? 0) || null;
  const [projects, setProjects] = useState<Project[]>([]);
  const [gaps, setGaps] = useState<GapCandidate[]>([]);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [challengeTerms, setChallengeTerms] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const load = () => { void apiRequest<Project[]>('/projects').then(setProjects); void apiRequest<GapCandidate[]>('/gaps').then(setGaps); };
  useEffect(load, []);

  const generate = async () => {
    if (!projectId || !papers.length) { message.error('请选择研究项目，并显式选择至少一篇论文'); return; }
    setError(null);
    try {
      const paperSet = await apiRequest<PaperSet>('/paper-sets', { method: 'POST', body: JSON.stringify({ project_id: projectId, purpose: 'gap', name: `候选空白证据集 · ${new Date().toLocaleString()}`, paper_ids: papers.map((paper) => paper.id), source_kind: initialPaperSetId ? 'favorites' : initialSessionId ? 'search_session' : 'explicit' }) });
      await apiRequest('/gaps/generate', { method: 'POST', body: JSON.stringify({ project_id: projectId, paper_set_id: paperSet.id }) });
      message.success('候选研究空白及可解释性分析已生成；当前仍不是创新性证明'); load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  const challenge = async (gap: GapCandidate) => {
    const additional_terms = (challengeTerms[gap.id] ?? '').split(',').map((term) => term.trim()).filter(Boolean);
    try { await apiRequest(`/gaps/${gap.id}/challenge`, { method: 'POST', body: JSON.stringify({ additional_terms }) }); message.success('Challenge Search 已完成；解释 Agent 已追加新版本，等待真实人工确认'); load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  const confirm = async (gap: GapCandidate) => { await apiRequest(`/gaps/${gap.id}/confirm`, { method: 'POST', body: JSON.stringify({ confirmed: true, note: '用户在 ResearchNavigator 界面显式人工确认' }) }); message.success('已记录真实界面人工确认'); load(); };
  const createPlan = async (gap: GapCandidate) => { await apiRequest('/plans', { method: 'POST', body: JSON.stringify({ project_id: gap.project_id, gap_id: gap.id }) }); message.success('研究计划已创建'); };

  return <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <Alert type="warning" showIcon title="候选研究空白是证据边界下的研究假设，不是创新性证明" description="输入由你显式选择的论文集合 + 自己选择的研究方向组成。解释层会区分直接证据、系统推断、缺失证据、削弱证据和 novelty risk；Challenge Search 完成后仍需你本人确认。" />
    {error && <Alert type="error" showIcon title="候选研究空白流程失败" description={error} />}
    <Card title="生成候选研究空白"><Form layout="vertical"><Form.Item label="研究项目 / 方向" required><Select placeholder="选择自己的研究方向" value={projectId ?? undefined} options={projects.map((project) => ({ value: project.id, label: `${project.name}${project.broad_direction ? ` · ${project.broad_direction}` : ''}` }))} onChange={setProjectId} /></Form.Item><Form.Item label="证据论文"><PaperSelectionPanel purpose="gap" ariaLabel="选择用于候选研究空白的论文" initialPaperSetId={initialPaperSetId} initialSessionId={initialSessionId} selected={papers} onChange={setPapers} /></Form.Item><Button type="primary" disabled={!projectId || !papers.length} onClick={() => void generate()}>构建证据矩阵并解释候选空白</Button></Form></Card>
    <List dataSource={gaps} locale={{ emptyText: '尚未生成候选研究空白' }} renderItem={(gap) => <List.Item><Card style={{ width: '100%' }} title={<Space wrap><Tag>{gap.status}</Tag><Tag color="blue">{gap.workflow_stage}</Tag><Tag>{gap.confidence}</Tag><Tag>paperSet #{gap.paper_set_id ?? 'legacy'}</Tag></Space>}>
      <Typography.Paragraph strong>{gap.claim}</Typography.Paragraph>
      <Descriptions bordered column={1} size="small"><Descriptions.Item label="研究问题建议">{gap.suggested_research_question}</Descriptions.Item><Descriptions.Item label="作用范围">{gap.scope}</Descriptions.Item><Descriptions.Item label="固定边界">not_novelty_proof={String(gap.not_novelty_proof)}</Descriptions.Item><Descriptions.Item label="最小验证">{stringList(gap.minimal_validation)}</Descriptions.Item><Descriptions.Item label="风险因素">{stringList(gap.risk_factors)}</Descriptions.Item></Descriptions>
      {gap.explanation && <Card size="small" title={`Gap Explanation Agent · v${gap.explanation.version} · ${gap.explanation.provider}`} style={{ marginTop: 16 }}><Descriptions column={1} size="small"><Descriptions.Item label="直接证据">{stringList(gap.explanation.direct_evidence)}</Descriptions.Item><Descriptions.Item label="系统推断（非论文直接陈述）">{stringList(gap.explanation.inferences)}</Descriptions.Item><Descriptions.Item label="支持论文 IDs">{gap.explanation.supporting_papers.join(', ') || '无'}</Descriptions.Item><Descriptions.Item label="削弱论文 IDs">{gap.explanation.weakening_papers.join(', ') || '无'}</Descriptions.Item><Descriptions.Item label="缺失证据">{stringList(gap.explanation.absent_evidence)}</Descriptions.Item><Descriptions.Item label="与当前方向关系">{JSON.stringify(gap.explanation.direction_relation)}</Descriptions.Item><Descriptions.Item label="Novelty 风险">{stringList(gap.explanation.novelty_risk_factors)}</Descriptions.Item><Descriptions.Item label="置信说明">{gap.explanation.confidence_rationale}</Descriptions.Item><Descriptions.Item label="不可越界">not_novelty_proof={String(gap.explanation.not_novelty_proof)}</Descriptions.Item></Descriptions></Card>}
      <Space orientation="vertical" style={{ width: '100%', marginTop: 16 }}><Input value={challengeTerms[gap.id] ?? ''} onChange={(event) => setChallengeTerms((current) => ({ ...current, [gap.id]: event.target.value }))} placeholder="可选：补充 Challenge Search 反证词，逗号分隔" /><Space wrap><Button onClick={() => void challenge(gap)}>执行 Challenge Search</Button><Button type="primary" disabled={gap.status !== 'pending_confirmation'} onClick={() => void confirm(gap)}>我已人工审阅并确认</Button><Button disabled={gap.status !== 'confirmed'} onClick={() => void createPlan(gap)}>创建研究计划</Button></Space></Space>
    </Card></List.Item>} />
  </Space>;
}
