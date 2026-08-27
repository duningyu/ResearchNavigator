import { Alert, Button, Card, Descriptions, List, Space, Tag, Typography } from 'antd';
import type { EvidenceWorkflow, SourceStatus } from '../types/domain';

type Props = {
  workflow: EvidenceWorkflow | null;
  busy: boolean;
  onRun: () => void;
  onCancel: () => void;
  onRefresh: () => void;
};

function valueText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未提供';
  if (typeof value === 'string') return value;
  try { return JSON.stringify(value, null, 2); } catch { return String(value); }
}

function sourceRows(workflow: EvidenceWorkflow): Array<[string, SourceStatus]> {
  const raw = workflow.result.source_status;
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return [];
  return Object.entries(raw).filter(([, value]) => Boolean(value) && typeof value === 'object') as Array<[string, SourceStatus]>;
}

function warnings(workflow: EvidenceWorkflow): string[] {
  const raw = workflow.result.warnings;
  return Array.isArray(raw) ? raw.map(String) : [];
}

export function EvidenceWorkflowPanel({ workflow, busy, onRun, onCancel, onRefresh }: Props) {
  if (!workflow) return <Alert type="info" showIcon title="尚未创建完整证据工作流" description="现有摘要补证接口仍可使用；完整工作流会继续执行开放全文许可判断、安全下载、全文解析、结构化分析以及作者卡和数据集卡刷新。" />;
  const sources = sourceRows(workflow);
  const warningRows = warnings(workflow);
  const statusColor = workflow.status === 'succeeded' ? 'green' : workflow.status === 'partial' ? 'orange' : workflow.status === 'failed' ? 'red' : workflow.status === 'cancelled' ? 'default' : 'blue';
  return <Card title="证据获取工作流" extra={<Space wrap><Tag color={statusColor}>{workflow.status}</Tag><Tag>{workflow.strongest_evidence}</Tag></Space>}>
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Descriptions bordered size="small" column={{ xs: 1, md: 2 }}>
        <Descriptions.Item label="工作流 ID">#{workflow.id}</Descriptions.Item>
        <Descriptions.Item label="最终证据等级">{workflow.strongest_evidence}</Descriptions.Item>
        <Descriptions.Item label="执行次数">{workflow.attempt_count}/{workflow.max_attempts}</Descriptions.Item>
        <Descriptions.Item label="terminal">{String(workflow.terminal)}</Descriptions.Item>
        <Descriptions.Item label="开始时间">{workflow.started_at ?? '未开始'}</Descriptions.Item>
        <Descriptions.Item label="结束时间">{workflow.finished_at ?? workflow.cancelled_at ?? '未完成'}</Descriptions.Item>
      </Descriptions>
      {warningRows.length > 0 && <Alert type="warning" showIcon title="工作流存在降级或失败步骤" description={warningRows.join('；')} />}
      {workflow.error && <Alert type="error" showIcon title="工作流失败" description={workflow.error} />}
      {sources.length > 0 && <Space wrap>{sources.map(([name, status]) => <Tag key={name} color={status.status === 'ok' ? 'green' : status.status === 'rate_limited' ? 'orange' : status.status === 'error' ? 'red' : 'default'}>{name}: {status.status}{status.detail ? ` · ${status.detail}` : ''}</Tag>)}</Space>}
      <Space wrap>
        {workflow.status === 'pending' && <Button type="primary" loading={busy} onClick={onRun}>运行证据工作流</Button>}
        {!workflow.terminal && <Button danger loading={busy} onClick={onCancel}>取消工作流</Button>}
        <Button loading={busy} onClick={onRefresh}>刷新状态</Button>
      </Space>
      <List
        header={<Typography.Text strong>证据工作流时间线</Typography.Text>}
        dataSource={workflow.events}
        locale={{ emptyText: '暂无事件；pending 只表示已入队，不代表 Worker 正常。' }}
        renderItem={(event) => <List.Item>
          <List.Item.Meta title={<Space><Tag>{event.event_type}</Tag><Typography.Text type="secondary">{event.created_at}</Typography.Text></Space>} description={<pre className="inline-json">{valueText(event.detail)}</pre>} />
        </List.Item>}
      />
    </Space>
  </Card>;
}
