import { Alert, Button, Card, Checkbox, Descriptions, Form, InputNumber, Select, Space, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { apiRequest } from '../api/client';

type ConfigStatus = {
  semantic_scholar_key_configured: boolean;
  openalex_api_key_configured: boolean;
  llm_key_configured: boolean;
  analysis_provider: string;
  analysis_prompt_version: string;
};
type RuntimeConfig = { source_health_timeout_seconds: number; worker_max_attempts_default: number };
type BackfillJob = {
  id: number;
  status: string;
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  error?: string | null;
  attempt_count: number;
  max_attempts: number;
  terminal: boolean;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

export function AdminPage() {
  const [form] = Form.useForm<RuntimeConfig>();
  const [status, setStatus] = useState<ConfigStatus | null>(null);
  const [backfill, setBackfill] = useState<BackfillJob | null>(null);
  const [dryRun, setDryRun] = useState(true);
  const [batchSize, setBatchSize] = useState(25);
  const [sources, setSources] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([apiRequest<ConfigStatus>('/admin/config-status'), apiRequest<RuntimeConfig>('/admin/runtime-config')])
      .then(([nextStatus, runtime]) => { setStatus(nextStatus); form.setFieldsValue(runtime); })
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  const save = async (values: RuntimeConfig) => {
    try {
      form.setFieldsValue(await apiRequest<RuntimeConfig>('/admin/runtime-config', { method: 'PUT', body: JSON.stringify(values) }));
      message.success('管理员运行配置已保存');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  const createBackfill = async () => {
    setBusy(true); setError(null);
    try {
      const job = await apiRequest<BackfillJob>('/admin/backfills/abstract-provenance', { method: 'POST', body: JSON.stringify({ dry_run: dryRun, batch_size: batchSize, sources }) });
      setBackfill(job);
      message.success(dryRun ? '历史摘要回填 dry-run 已创建；不会修改论文或证据等级' : '历史摘要回填任务已创建；只会提升重新获取且身份严格匹配的摘要');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };
  const runBackfill = async () => {
    if (!backfill) return;
    setBusy(true); setError(null);
    try {
      const job = await apiRequest<BackfillJob>(`/admin/backfills/${backfill.id}/run`, { method: 'POST' });
      setBackfill(job);
      message.success('历史摘要回填执行结束；请按分类结果核对真实提升和未处理项');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };
  const refreshBackfill = async () => {
    if (!backfill) return;
    setBusy(true);
    try { setBackfill(await apiRequest<BackfillJob>(`/admin/backfills/${backfill.id}`)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };
  const cancelBackfill = async () => {
    if (!backfill) return;
    setBusy(true);
    try { setBackfill(await apiRequest<BackfillJob>(`/admin/backfills/${backfill.id}/cancel`, { method: 'POST' })); message.info('历史摘要回填任务已取消'); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  return <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <Alert type="warning" showIcon title="管理员配置只暴露布尔状态和白名单参数" description="任何 OpenAlex、Semantic Scholar、LLM 或机构订阅凭据都不会返回浏览器。" />
    {error && <Alert type="error" showIcon title="管理员操作失败" description={error} />}
    <Card title="服务端凭据与分析状态"><Descriptions bordered column={1}>
      <Descriptions.Item label="OpenAlex API Key">{status ? <Tag color={status.openalex_api_key_configured ? 'green' : 'default'}>{status.openalex_api_key_configured ? 'configured' : 'not configured'}</Tag> : '读取中'}</Descriptions.Item>
      <Descriptions.Item label="Semantic Scholar API Key">{status ? <Tag color={status.semantic_scholar_key_configured ? 'green' : 'default'}>{status.semantic_scholar_key_configured ? 'configured' : 'not configured'}</Tag> : '读取中'}</Descriptions.Item>
      <Descriptions.Item label="LLM Provider Key">{status ? <Tag color={status.llm_key_configured ? 'green' : 'default'}>{status.llm_key_configured ? 'configured' : 'not configured'}</Tag> : '读取中'}</Descriptions.Item>
      <Descriptions.Item label="Analysis Provider / Prompt">{status ? `${status.analysis_provider} / ${status.analysis_prompt_version}` : '读取中'}</Descriptions.Item>
    </Descriptions></Card>
    <Card title="可热更新运行参数"><Form form={form} layout="vertical" onFinish={(values) => void save(values)}>
      <Form.Item name="source_health_timeout_seconds" label="来源主动测试超时（秒）" rules={[{ required: true }]}><InputNumber min={0.5} max={30} step={0.5} /></Form.Item>
      <Form.Item name="worker_max_attempts_default" label="Worker 默认最大尝试次数" rules={[{ required: true }]}><InputNumber min={1} max={10} /></Form.Item>
      <Button type="primary" htmlType="submit">保存运行配置</Button>
    </Form></Card>
    <Card title="历史摘要可信回填">
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Alert type="warning" showIcon title="不会直接把旧摘要标记为可信" description="迁移后 provides_abstract=0 是正确的。任务必须通过 DOI、arXiv ID 或严格标题+年份重新获取非 fixture 摘要，记录 PaperSource provenance 后才可提升证据等级并生成新分析版本。" />
        <Space wrap align="end">
          <Checkbox checked={dryRun} onChange={(event) => setDryRun(event.target.checked)}>dry_run（只报告 would_verify，不修改数据）</Checkbox>
          <label><Typography.Text>批大小</Typography.Text><br /><InputNumber aria-label="回填批大小" min={1} max={500} value={batchSize} onChange={(value) => setBatchSize(value ?? 25)} /></label>
          <label><Typography.Text>限制来源（留空=全部合格来源）</Typography.Text><br /><Select aria-label="回填来源" mode="multiple" allowClear style={{ minWidth: 360 }} value={sources} onChange={setSources} options={['crossref', 'arxiv', 'semantic_scholar', 'openalex'].map((value) => ({ value, label: value }))} /></label>
          <Button type="primary" loading={busy} onClick={() => void createBackfill()}>创建回填任务</Button>
        </Space>
        <Typography.Paragraph type="secondary">结果分类包括 verified_and_updated、verified_same_text、already_verified、identifier_conflict、title_year_mismatch、no_trusted_abstract、source_unavailable 和 skipped_fixture。</Typography.Paragraph>
        {backfill && <Descriptions bordered size="small" column={1}>
          <Descriptions.Item label="Job / Status">#{backfill.id} · <Tag color={backfill.status === 'succeeded' ? 'green' : backfill.status === 'failed' ? 'red' : 'blue'}>{backfill.status}</Tag> · attempts={backfill.attempt_count}/{backfill.max_attempts}</Descriptions.Item>
          <Descriptions.Item label="Payload"><pre className="inline-json">{JSON.stringify(backfill.payload, null, 2)}</pre></Descriptions.Item>
          <Descriptions.Item label="Result"><pre className="inline-json">{JSON.stringify(backfill.result, null, 2)}</pre></Descriptions.Item>
          <Descriptions.Item label="Error">{backfill.error ?? '无'}</Descriptions.Item>
        </Descriptions>}
        {backfill && <Space wrap>{backfill.status === 'pending' && <Button type="primary" loading={busy} onClick={() => void runBackfill()}>运行回填</Button>}<Button loading={busy} onClick={() => void refreshBackfill()}>刷新</Button>{!backfill.terminal && <Button danger loading={busy} onClick={() => void cancelBackfill()}>取消</Button>}</Space>}
      </Space>
    </Card>
  </Space>;
}
