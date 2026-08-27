import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Descriptions,
  Input,
  InputNumber,
  List,
  Radio,
  Row,
  Select,
  Space,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import { useEffect, useState } from 'react';
import { apiRequest } from '../api/client';
import type { EvaluationAssignment, EvaluationResult, EvaluationStudy } from '../types/domain';

type RatingDraft = {
  evidence_correctness: number;
  evidence_sufficiency: number;
  citation_usefulness: number;
  missing_field_correctness: number;
  preference: 'A' | 'B' | 'tie';
  comments: string;
};

const AWAITING_REAL_EXPERTS = 'awaiting_real_experts';

const defaultRating: RatingDraft = {
  evidence_correctness: 4,
  evidence_sufficiency: 4,
  citation_usefulness: 4,
  missing_field_correctness: 4,
  preference: 'tie',
  comments: '',
};

function safeObject(value: string, label: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(value);
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) throw new Error(`${label} 必须是 JSON object`);
  return parsed as Record<string, unknown>;
}

export function EvaluationsPage() {
  const [assignments, setAssignments] = useState<EvaluationAssignment[]>([]);
  const [studies, setStudies] = useState<EvaluationStudy[]>([]);
  const [ratings, setRatings] = useState<Record<number, RatingDraft>>({});
  const [studyName, setStudyName] = useState('证据解释盲评');
  const [description, setDescription] = useState('比较基线分析与证据增强分析，不显示系统身份。');
  const [studyVersion, setStudyVersion] = useState('expert-study-v1');
  const [seed, setSeed] = useState(`study-${new Date().toISOString().slice(0, 10)}`);
  const [minimumExperts, setMinimumExperts] = useState(2);
  const [taskKey, setTaskKey] = useState('paper-analysis-1');
  const [baselineJson, setBaselineJson] = useState('{"summary":"基线输出","citations":[]}');
  const [candidateJson, setCandidateJson] = useState('{"summary":"候选输出","citations":[]}');
  const [selectedStudyId, setSelectedStudyId] = useState<number | null>(null);
  const [expertUserId, setExpertUserId] = useState<number | null>(null);
  const [simulatedAssignment, setSimulatedAssignment] = useState(false);
  const [result, setResult] = useState<EvaluationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAssignments = async () => {
    try { setAssignments(await apiRequest<EvaluationAssignment[]>('/evaluations/assignments')); }
    catch { setAssignments([]); }
  };
  const loadStudies = async () => {
    try {
      const values = await apiRequest<EvaluationStudy[]>('/evaluations/studies');
      setStudies(values);
      if (!selectedStudyId && values.length) setSelectedStudyId(values[0].id);
    } catch { setStudies([]); }
  };
  useEffect(() => { void loadAssignments(); void loadStudies(); }, []);

  const createStudy = async () => {
    setBusy(true); setError(null);
    try {
      const study = await apiRequest<EvaluationStudy>('/evaluations/studies', {
        method: 'POST',
        body: JSON.stringify({
          name: studyName,
          description,
          study_version: studyVersion,
          randomized_seed: seed,
          protocol: {
            minimum_real_experts: minimumExperts,
            score_scale: [1, 5],
            dimensions: ['evidence_correctness', 'evidence_sufficiency', 'citation_usefulness', 'missing_field_correctness'],
          },
          tasks: [{
            task_key: taskKey,
            paper_id: null,
            baseline_payload: safeObject(baselineJson, '基线输出'),
            candidate_payload: safeObject(candidateJson, '候选输出'),
            position: 1,
          }],
        }),
      });
      setSelectedStudyId(study.id);
      await loadStudies();
      message.success('评测研究已创建为 draft；冻结前仍可检查协议');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const freeze = async (studyId: number) => {
    setBusy(true); setError(null);
    try {
      await apiRequest(`/evaluations/studies/${studyId}/freeze`, { method: 'POST' });
      await loadStudies();
      message.success('协议和任务已冻结，输入哈希已持久化');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const assign = async () => {
    if (!selectedStudyId || !expertUserId) { message.error('请选择研究并填写评审者 user_id'); return; }
    setBusy(true); setError(null);
    try {
      await apiRequest(`/evaluations/studies/${selectedStudyId}/assignments`, {
        method: 'POST',
        body: JSON.stringify({ expert_user_id: expertUserId, is_simulated: simulatedAssignment }),
      });
      message.success(simulatedAssignment ? '模拟评测任务已创建，并永久标记为 simulated' : '盲评任务已分配');
      await loadStudies();
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const start = async (assignmentId: number) => {
    await apiRequest(`/evaluations/assignments/${assignmentId}/start`, { method: 'POST' });
    await loadAssignments();
  };

  const submit = async (assignmentId: number) => {
    const payload = ratings[assignmentId] ?? defaultRating;
    setBusy(true); setError(null);
    try {
      await apiRequest(`/evaluations/assignments/${assignmentId}/ratings`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      await loadAssignments();
      message.success('评分已提交；盲序映射只用于聚合，不在评测界面暴露');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const loadResults = async (studyId: number) => {
    setBusy(true); setError(null);
    try { setResult(await apiRequest<EvaluationResult>(`/evaluations/studies/${studyId}/results`)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const reviewerTab = <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <Alert type="warning" showIcon title="模拟或开发者评分不能作为真实专家验证" description="只有明确标记为非模拟、由独立评审者实际提交且满足冻结协议最低人数的结果，系统才显示 real_expert_results_available；这仍不等同于自动验证评审者资质。" />
    <List
      dataSource={assignments}
      locale={{ emptyText: '当前账号没有待评测任务。' }}
      renderItem={(assignment) => {
        const draft = ratings[assignment.id] ?? defaultRating;
        return <List.Item>
          <Card style={{ width: '100%' }} title={`任务：${assignment.task_key}`} extra={<Space><Tag>{assignment.status}</Tag>{assignment.is_simulated && <Tag color="orange">simulated</Tag>}</Space>}>
            <Row gutter={[16, 16]}>
              {assignment.variants.map((variant) => <Col xs={24} lg={12} key={variant.label}><Card size="small" title={`方案 ${variant.label}`}><pre className="inline-json">{JSON.stringify(variant.payload, null, 2)}</pre></Card></Col>)}
            </Row>
            {assignment.status === 'assigned' && <Button type="primary" onClick={() => void start(assignment.id)}>开始盲评</Button>}
            {assignment.status === 'started' && <Space orientation="vertical" style={{ width: '100%', marginTop: 16 }}>
              <Descriptions bordered column={1} size="small">
                {([
                  ['evidence_correctness', '证据正确性'],
                  ['evidence_sufficiency', '证据充分性'],
                  ['citation_usefulness', '引用可用性'],
                  ['missing_field_correctness', '缺失字段判断正确性'],
                ] as const).map(([key, label]) => <Descriptions.Item key={key} label={label}><InputNumber min={1} max={5} value={draft[key]} onChange={(value) => setRatings((current) => ({ ...current, [assignment.id]: { ...draft, [key]: value ?? 1 } }))} /></Descriptions.Item>)}
              </Descriptions>
              <Radio.Group value={draft.preference} onChange={(event) => setRatings((current) => ({ ...current, [assignment.id]: { ...draft, preference: event.target.value as RatingDraft['preference'] } }))} options={[{ label: '方案 A 更好', value: 'A' }, { label: '方案 B 更好', value: 'B' }, { label: '无明显偏好', value: 'tie' }]} />
              <Input.TextArea placeholder="可选评语" value={draft.comments} onChange={(event) => setRatings((current) => ({ ...current, [assignment.id]: { ...draft, comments: event.target.value } }))} />
              <Button type="primary" loading={busy} onClick={() => void submit(assignment.id)}>提交评分</Button>
            </Space>}
            {assignment.status === 'completed' && <Alert style={{ marginTop: 12 }} type="success" showIcon title="已完成" description="该 assignment 只允许一条评分记录，避免重复提交污染结果。" />}
          </Card>
        </List.Item>;
      }}
    />
  </Space>;

  const ownerTab = <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <Alert type="info" showIcon title="先冻结协议，再创建盲评任务" description="冻结哈希覆盖研究版本、协议、基线/候选输出和任务顺序。冻结后不能修改，避免根据结果调整评测口径。" />
    <Card title="创建评测研究">
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}><Typography.Text>研究名称</Typography.Text><Input value={studyName} onChange={(event) => setStudyName(event.target.value)} /></Col>
        <Col xs={24} md={12}><Typography.Text>研究版本</Typography.Text><Input value={studyVersion} onChange={(event) => setStudyVersion(event.target.value)} /></Col>
        <Col xs={24}><Typography.Text>研究说明</Typography.Text><Input.TextArea value={description} onChange={(event) => setDescription(event.target.value)} /></Col>
        <Col xs={24} md={12}><Typography.Text>随机种子</Typography.Text><Input value={seed} onChange={(event) => setSeed(event.target.value)} /></Col>
        <Col xs={24} md={12}><Typography.Text>每个任务最低真实评审人数</Typography.Text><InputNumber min={1} max={20} value={minimumExperts} onChange={(value) => setMinimumExperts(value ?? 2)} /></Col>
        <Col xs={24}><Typography.Text>任务键</Typography.Text><Input value={taskKey} onChange={(event) => setTaskKey(event.target.value)} /></Col>
        <Col xs={24} lg={12}><Typography.Text>基线输出 JSON</Typography.Text><Input.TextArea rows={8} value={baselineJson} onChange={(event) => setBaselineJson(event.target.value)} /></Col>
        <Col xs={24} lg={12}><Typography.Text>候选输出 JSON</Typography.Text><Input.TextArea rows={8} value={candidateJson} onChange={(event) => setCandidateJson(event.target.value)} /></Col>
      </Row>
      <Button style={{ marginTop: 16 }} type="primary" loading={busy} onClick={() => void createStudy()}>创建 draft</Button>
    </Card>

    <Card title="研究与冻结状态">
      <List dataSource={studies} locale={{ emptyText: '尚无评测研究。' }} renderItem={(study) => <List.Item actions={[
        study.status === 'draft' ? <Button key="freeze" onClick={() => void freeze(study.id)}>冻结协议</Button> : null,
        <Button key="result" onClick={() => void loadResults(study.id)}>查看聚合</Button>,
      ].filter(Boolean)}>
        <List.Item.Meta title={<Space wrap><Typography.Text strong>{study.name}</Typography.Text><Tag>{study.status}</Tag><Tag color={study.expert_outcome_validation === 'real_expert_results_available' ? 'green' : 'orange'}>{study.expert_outcome_validation}</Tag></Space>} description={<Space orientation="vertical"><Typography.Text type="secondary">{study.description}</Typography.Text><Typography.Text code>{study.frozen_input_hash ?? '尚未冻结'}</Typography.Text></Space>} />
      </List.Item>} />
    </Card>

    <Card title="分配盲评任务">
      <Space wrap>
        <Select style={{ minWidth: 280 }} placeholder="选择已冻结研究" value={selectedStudyId ?? undefined} onChange={setSelectedStudyId} options={studies.map((study) => ({ value: study.id, label: `${study.name} · ${study.status}`, disabled: study.status === 'draft' }))} />
        <InputNumber placeholder="评审者 user_id" min={1} value={expertUserId ?? undefined} onChange={(value) => setExpertUserId(value)} />
        <Checkbox checked={simulatedAssignment} onChange={(event) => setSimulatedAssignment(event.target.checked)}>这是模拟/开发者评测</Checkbox>
        <Button type="primary" loading={busy} onClick={() => void assign()}>创建 assignments</Button>
      </Space>
    </Card>

    {result && <Card title="评测聚合结果">
      <Alert type={result.validation_status === 'real_expert_results_available' ? 'success' : 'warning'} showIcon title={result.validation_status} description={result.claim_boundary} />
      <Descriptions bordered column={1} style={{ marginTop: 16 }}>
        <Descriptions.Item label="真实评审人数">{result.real_expert_count}</Descriptions.Item>
        <Descriptions.Item label="模拟评审人数">{result.simulated_count}</Descriptions.Item>
        <Descriptions.Item label="指标"><pre className="inline-json">{JSON.stringify(result.metrics, null, 2)}</pre></Descriptions.Item>
      </Descriptions>
    </Card>}
  </Space>;

  return <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <Alert type="warning" showIcon title={AWAITING_REAL_EXPERTS} description="在真实评审者完成冻结任务且达到协议要求前，专家效果验证保持 awaiting_real_experts。模拟或开发者评分不能作为真实专家验证，LLM 评分也不能作为专家真值。" />
    {error && <Alert type="error" showIcon title="专家评测操作失败" description={error} />}
    <Tabs items={[{ key: 'reviewer', label: '我的盲评任务', children: reviewerTab }, { key: 'owner', label: '评测研究管理', children: ownerTab }]} />
  </Space>;
}
