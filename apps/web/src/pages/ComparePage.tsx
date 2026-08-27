import { Alert, Button, Card, Form, Select, Space, Table, Tag, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiRequest } from '../api/client';
import { PaperSelectionPanel } from '../components/PaperSelectionPanel';
import type { ComparisonRun, Paper, PaperSet, Project } from '../types/domain';

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '证据不足';
  if (Array.isArray(value)) return value.length ? value.map(displayValue).join('；') : '证据不足';
  if (typeof value === 'object') return Object.entries(value as Record<string, unknown>).map(([key, entry]) => `${key}: ${displayValue(entry)}`).join('；');
  return String(value);
}

export function ComparePage() {
  const [params] = useSearchParams();
  const initialPaperSetId = Number(params.get('paperSet') ?? 0) || null;
  const initialSessionId = Number(params.get('session') ?? 0) || null;
  const [projects, setProjects] = useState<Project[]>([]);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [comparison, setComparison] = useState<ComparisonRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => { void apiRequest<Project[]>('/projects').then(setProjects).catch(() => setProjects([])); }, []);

  const runComparison = async () => {
    if (!projectId || papers.length < 2) return;
    setLoading(true); setError(null);
    try {
      const paperSet = await apiRequest<PaperSet>('/paper-sets', { method: 'POST', body: JSON.stringify({ project_id: projectId, purpose: 'compare', name: `论文对比 · ${new Date().toLocaleString()}`, paper_ids: papers.map((paper) => paper.id), source_kind: initialPaperSetId ? 'favorites' : initialSessionId ? 'search_session' : 'explicit' }) });
      setComparison(await apiRequest<ComparisonRun>('/comparisons', { method: 'POST', body: JSON.stringify({ project_id: projectId, paper_set_id: paperSet.id }) }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setLoading(false); }
  };

  const tableRows = useMemo(() => comparison?.rows.map((row) => ({ key: row.key, label: row.label, ...Object.fromEntries(row.cells.map((cell) => [String(cell.paper_id), cell])) })) ?? [], [comparison]);
  const columns = useMemo(() => comparison ? [{ title: '研究维度', dataIndex: 'label', key: 'label', width: 180, fixed: 'left' as const }, ...comparison.papers.map((paper) => ({ title: <Space orientation="vertical" size={0}><Typography.Text strong>{paper.title}</Typography.Text><Tag>{paper.evidence_level}</Tag></Space>, dataIndex: String(paper.id), key: String(paper.id), width: 330, render: (cell: { value: unknown; evidence_state: string; citations: unknown[] } | undefined) => cell ? <Space orientation="vertical" size={5}><Typography.Text>{displayValue(cell.value)}</Typography.Text><Space wrap><Tag color={cell.evidence_state === 'evidenced' ? 'green' : cell.evidence_state === 'insufficient_evidence' ? 'orange' : 'default'}>{cell.evidence_state}</Tag><Tag>{cell.citations.length} citations</Tag></Space></Space> : '证据不足' }))] : [], [comparison]);

  return <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <Alert type="info" showIcon title="论文对比现在由“显式论文集合 + 你选择的研究方向”驱动" description="不会再自动读取上一次搜索。比较字段覆盖研究问题、任务、输入输出、方法/理论创新、研究路线、数据集、指标、切分协议、结果、Future Work、局限、证据等级和与当前方向的关联程度。" />
    {error && <Alert type="error" showIcon title="生成对比失败" description={error} />}
    <Card title="选择论文与研究方向">
      <Form layout="vertical"><Form.Item label="研究项目 / 方向" required><Select placeholder="选择自己的研究方向" value={projectId ?? undefined} options={projects.map((project) => ({ value: project.id, label: `${project.name}${project.broad_direction ? ` · ${project.broad_direction}` : ''}` }))} onChange={setProjectId} /></Form.Item><Form.Item label="论文集合"><PaperSelectionPanel purpose="compare" ariaLabel="选择用于对比的论文" initialPaperSetId={initialPaperSetId} initialSessionId={initialSessionId} selected={papers} onChange={setPapers} /></Form.Item><Button type="primary" loading={loading} disabled={!projectId || papers.length < 2} onClick={() => void runComparison()}>生成证据级对比矩阵</Button></Form>
    </Card>
    {comparison && <Card title={`证据级对比矩阵 #${comparison.id}`} extra={<Space><Tag>{comparison.analysis_version}</Tag><Tag>hash={comparison.evidence_hash.slice(0, 12)}…</Tag></Space>}><Typography.Paragraph type="secondary">方向快照已固化在本次 comparison run 中。摘要级论文对应字段会明确显示“证据不足”，不会用元数据填充实验协议或 Future Work。</Typography.Paragraph><Table pagination={false} scroll={{ x: Math.max(900, comparison.papers.length * 330) }} dataSource={tableRows} columns={columns} /></Card>}
  </Space>;
}
