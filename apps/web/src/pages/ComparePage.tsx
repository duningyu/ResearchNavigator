import { Alert, Button, Card, Form, Select, Space, Table, Tabs, Tag, Typography } from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../api/client';
import { PaperSelectionPanel } from '../components/PaperSelectionPanel';
import { evidenceText, gapState } from '../lib/researchDisplay';
import { readingOrder } from '../lib/comparisonReading';
import type { ComparisonRun, Paper, PaperSet, Project } from '../types/domain';
import { GapsPage } from './GapsPage';

export function ComparePage() {
  const [params, setParams] = useSearchParams();
  const activeKey = params.get('tab') === 'opportunities' ? 'opportunities' : 'comparison';
  return <Tabs activeKey={activeKey} onChange={(key) => {
    const next = new URLSearchParams(params);
    next.set('tab', key);
    setParams(next);
  }} items={[
    { key: 'comparison', label: '比较论文', children: <ComparisonWorkspace /> },
    { key: 'opportunities', label: '核实研究机会', children: <GapsPage /> },
  ]} />;
}

function ComparisonWorkspace() {
  const [params, setParams] = useSearchParams();
  const initialPaperSetId = Number(params.get('paperSet') ?? 0) || null;
  const initialSessionId = Number(params.get('session') ?? 0) || null;
  const initialSelectedIds = useMemo(() => params.get('papers')?.split(',').map(Number).filter((id) => Number.isSafeInteger(id) && id > 0), [params]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [projectId, setProjectId] = useState<number | null>(Number(params.get('project')) || null);
  const [comparison, setComparison] = useState<ComparisonRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const generation = useRef(0);
  const savedId = Number(params.get('comparison')) || null;
  useEffect(() => { void apiRequest<Project[]>('/projects').then(setProjects).catch(() => setProjects([])); }, []);
  useEffect(() => {
    const request = ++generation.current;
    setComparison(null);
    setLoading(false);
    if (savedId && Number.isSafeInteger(savedId) && savedId > 0) {
      void apiRequest<ComparisonRun>(`/comparisons/${savedId}`).then((saved) => {
        if (request !== generation.current) return;
        if ((projectId && saved.project_id !== projectId) || (initialPaperSetId && saved.paper_set_id !== initialPaperSetId)) {
          setError('已保存对比与当前方向或论文集合不一致，请重新选择。');
          return;
        }
        setComparison(saved);
      }).catch((reason) => { if (request === generation.current) setError(reason instanceof Error ? reason.message : '已保存对比暂不可读取，请重试。'); });
    }
    return () => { ++generation.current; };
  }, [savedId, projectId, initialPaperSetId]);

  const runComparison = async () => {
    if (!projectId || papers.length < 2) return;
    const request = ++generation.current;
    setLoading(true); setError(null);
    try {
      const paperSet = await apiRequest<PaperSet>('/paper-sets', { method: 'POST', body: JSON.stringify({ project_id: projectId, purpose: 'compare', name: `论文对比 · ${new Date().toLocaleString()}`, paper_ids: papers.map((paper) => paper.id), source_kind: initialPaperSetId ? 'favorites' : initialSessionId ? 'search_session' : 'explicit' }) });
      if (request !== generation.current) return;
      const saved = await apiRequest<ComparisonRun>('/comparisons', { method: 'POST', body: JSON.stringify({ project_id: projectId, paper_set_id: paperSet.id }) });
      if (request !== generation.current) return;
      setComparison(saved);
      const next = new URLSearchParams(params);
      next.set('project', String(projectId)); next.set('paperSet', String(paperSet.id)); next.set('comparison', String(saved.id));
      setParams(next, { replace: true });
    } catch (reason) { if (request === generation.current) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (request === generation.current) setLoading(false); }
  };

  const tableRows = useMemo(() => comparison?.rows.map((row) => ({ key: row.key, label: row.label, ...Object.fromEntries(row.cells.map((cell) => [String(cell.paper_id), cell])) })) ?? [], [comparison]);
  const columns = useMemo(() => comparison ? [{ title: '研究维度', dataIndex: 'label', key: 'label', width: 180, fixed: 'left' as const }, ...comparison.papers.map((paper) => ({ title: <Space orientation="vertical" size={0}><Typography.Text strong>{paper.title}</Typography.Text><Tag>{gapState(paper.evidence_level)}</Tag></Space>, dataIndex: String(paper.id), key: String(paper.id), width: 330, render: (cell: { value: unknown; evidence_state: string; citations: unknown[] } | undefined) => cell ? <Space orientation="vertical" size={5}><Typography.Text>{evidenceText(cell.value)}</Typography.Text><Space wrap><Tag color={cell.evidence_state === 'evidenced' ? 'green' : cell.evidence_state === 'insufficient_evidence' ? 'orange' : 'default'}>{gapState(cell.evidence_state)}</Tag><Tag>{cell.citations.length} 处引用</Tag></Space></Space> : '证据不足' }))] : [], [comparison]);

  return <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <Alert type="info" showIcon title="论文对比现在由“显式论文集合 + 你选择的研究方向”驱动" description="不会再自动读取上一次搜索。比较字段覆盖研究问题、任务、输入输出、方法/理论创新、研究路线、数据集、指标、切分协议、结果、Future Work、局限、证据等级和与当前方向的关联程度。" />
    {error && <Alert type="error" showIcon title="生成对比失败" description={error} />}
    <Card title="选择论文与研究方向">
      <Form layout="vertical"><Form.Item label="研究课题 / 方向" required><Select placeholder="选择自己的研究方向" value={projectId ?? undefined} options={projects.map((project) => ({ value: project.id, label: `${project.name}${project.broad_direction ? ` · ${project.broad_direction}` : ''}` }))} onChange={setProjectId} /></Form.Item><Form.Item label="论文集合"><PaperSelectionPanel purpose="compare" ariaLabel="选择用于对比的论文" initialPaperSetId={initialPaperSetId} initialSessionId={initialSessionId} initialSelectedIds={initialSelectedIds} selected={papers} onChange={setPapers} /></Form.Item><Button type="primary" loading={loading} disabled={!projectId || papers.length < 2} onClick={() => void runComparison()}>生成证据级对比矩阵</Button></Form>
    </Card>
    {comparison && <>
      <Card title="先看结论"><Typography.Paragraph>已对照所选 {comparison.papers.length} 篇论文。尚不能据此判断方法优劣：请先核对研究任务、数据与实验条件是否可比。</Typography.Paragraph>
        <Typography.Title level={4}>先读谁，为什么</Typography.Title>
        <Typography.Paragraph>{readingOrder(comparison).reason}</Typography.Paragraph>
        {readingOrder(comparison).priority.map((paper) => <Typography.Paragraph key={paper.id}><Link to={`/papers/${paper.id}`}>{paper.title}</Link>：先核对任务定义与原文依据，再决定是否用作对照。</Typography.Paragraph>)}
        {readingOrder(comparison).others.map((paper) => <Typography.Paragraph key={paper.id}><Link to={`/papers/${paper.id}`}>{paper.title}</Link>：保留为背景或待补材料，不能因证据缺失判定无价值。</Typography.Paragraph>)}
        <Typography.Paragraph>当前 {comparison.rows.filter((row) => row.cells.some((cell) => cell.evidence_state !== 'evidenced' || !cell.citations.length)).length} 个维度仍有待补充或定位的证据。缺失信息不代表作者没有研究，也不代表研究空白。</Typography.Paragraph>
        <Link to={`/gaps?project=${comparison.project_id}&paperSet=${comparison.paper_set_id}`}>继续核实研究机会</Link>
      </Card>
      <Card><details><summary>展开逐项核对依据</summary><Typography.Paragraph type="secondary">保留论文原文与书目名称。材料不足的字段不会用推测补齐；研究机会还需要单独通过相关性与证据核验。</Typography.Paragraph><Table pagination={false} scroll={{ x: Math.max(900, comparison.papers.length * 330) }} dataSource={tableRows} columns={columns} /></details></Card>
    </>}
  </Space>;
}
