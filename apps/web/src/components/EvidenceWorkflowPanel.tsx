import { Alert, Button, Card, Descriptions, List, Space, Tag, Typography } from 'antd';
import type { EvidenceWorkflow, SourceStatus } from '../types/domain';
import { evidenceEvent, gapState } from '../lib/researchDisplay';

type Props = {
  workflow: EvidenceWorkflow | null;
  busy: boolean;
  onRun: () => void;
  onCancel: () => void;
  onRefresh: () => void;
};

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
  const unverified = ['succeeded', 'partial'].includes(workflow.status) && workflow.result_integrity !== 'verified';
  const statusColor = workflow.status === 'succeeded' ? 'green' : workflow.status === 'partial' ? 'orange' : workflow.status === 'failed' ? 'red' : workflow.status === 'cancelled' ? 'default' : 'blue';
  return <Card title="材料获取进展" extra={<Space wrap><Tag color={unverified ? 'orange' : statusColor}>{unverified && workflow.status === 'succeeded' ? '结果尚未核验' : gapState(workflow.status)}</Tag><Tag>{gapState(workflow.strongest_evidence)}</Tag></Space>}>
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      {unverified && <Alert type="warning" showIcon title="请重新核对处理结果" description="任务结束不等于材料已准备好。尚未确认结果存在且属于当前论文与项目，请刷新核验后再继续。" />}
      <Descriptions bordered size="small" column={{ xs: 1, md: 2 }}>
        <Descriptions.Item label="现有材料">{gapState(workflow.strongest_evidence)}</Descriptions.Item>
        <Descriptions.Item label="处理进展">{workflow.terminal ? '本次处理已结束' : '仍在处理中，尚不能视为完成'}</Descriptions.Item>
        <Descriptions.Item label="开始时间">{workflow.started_at ?? '未开始'}</Descriptions.Item>
        <Descriptions.Item label="结束时间">{workflow.finished_at ?? workflow.cancelled_at ?? '未完成'}</Descriptions.Item>
      </Descriptions>
      {(warningRows.length > 0 || workflow.status === 'partial') && <Alert type="warning" showIcon title="材料仍有缺口" description="部分获取或分析步骤未完成，请核对下方来源状态。未能取得正文不表示论文收费；可先依据可信摘要阅读，也可补充你有权使用的材料。" />}
      {workflow.error && <Alert type="error" showIcon title="材料处理失败" description="本次处理未完成，请检查来源状态后重试；现有材料不作为完整正文证明。" />}
      {sources.length > 0 && <Space wrap>{sources.map(([name, status]) => <Tag key={name} color={status.status === 'ok' ? 'green' : status.status === 'rate_limited' ? 'orange' : status.status === 'error' ? 'red' : 'default'}>{name}: {gapState(status.status)}</Tag>)}</Space>}
      <Space wrap>
        {workflow.status === 'pending' && <Button type="primary" loading={busy} onClick={onRun}>运行证据工作流</Button>}
        {!workflow.terminal && <Button danger loading={busy} onClick={onCancel}>取消工作流</Button>}
        <Button loading={busy} onClick={onRefresh}>刷新状态</Button>
      </Space>
      <List
        header={<Typography.Text strong>证据工作流时间线</Typography.Text>}
        dataSource={workflow.events}
        locale={{ emptyText: '正在等待处理记录；提交请求不等于处理完成。' }}
        renderItem={(event) => <List.Item>
          <List.Item.Meta title={<Space><Tag>{evidenceEvent(event.event_type)}</Tag><Typography.Text type="secondary">{event.created_at}</Typography.Text></Space>} />
        </List.Item>}
      />
    </Space>
  </Card>;
}
