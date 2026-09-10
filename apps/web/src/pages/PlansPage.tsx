import { Alert, Button, Card, Form, Input, List, Modal, Progress, Space, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { apiRequest } from '../api/client';
import type { PlanItem, ResearchPlan } from '../types/domain';
import { planCategory } from '../lib/researchDisplay';

export function PlansPage() {
  const [plans, setPlans] = useState<ResearchPlan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<PlanItem | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();
  const fail = (reason: unknown) => setError(reason instanceof Error ? reason.message : '请求未完成，请重试');
  const load = () => void apiRequest<ResearchPlan[]>('/plans').then(setPlans).catch(fail);
  useEffect(load, []);
  const update = async (id: number, values: Partial<PlanItem>) => {
    setSaving(true);
    try {
      await apiRequest(`/plan-items/${id}`, { method: 'PUT', body: JSON.stringify(values) });
      message.success('行动记录已保存'); setEditing(null); load();
    } catch (reason) { fail(reason); } finally { setSaving(false); }
  };
  const stateLabels: Record<string, string> = { pending: '待开始', in_progress: '进行中', done: '已完成', skipped: '已跳过', blocked: '需补充条件' };
  return <>
    {error && <Alert type="error" title={error} />}
    <Typography.Paragraph>完成状态由你记录，不代表研究结论已验证。</Typography.Paragraph>
    <List dataSource={plans} locale={{ emptyText: '请先完成候选空白的反证检索和人工确认，再创建研究计划。' }} renderItem={(plan) => {
      const done = plan.items.filter((item) => item.status === 'done').length;
      return <List.Item><Card style={{ width: '100%' }} title={plan.title}>
        {plan.review_required && <Alert type="warning" title={plan.review_reason || '此计划的证据需要重新核验'} />}
        <Typography.Paragraph>{plan.objective}</Typography.Paragraph>
        <Progress percent={plan.items.length ? Math.round(done / plan.items.length * 100) : 0} />
        <List dataSource={plan.items} renderItem={(item) => <List.Item actions={[
          <Button key="edit" disabled={plan.review_required || saving} onClick={() => { setEditing(item); form.setFieldsValue(item); }}>编辑步骤</Button>,
          item.status === 'done' || item.status === 'skipped'
            ? <Button key="reopen" disabled={plan.review_required || saving} onClick={() => void update(item.id, { status: 'pending' })}>重新打开</Button>
            : <Space key="progress"><Button disabled={plan.review_required || saving} onClick={() => void update(item.id, { status: 'done' })}>完成</Button><Button disabled={plan.review_required || saving} onClick={() => void update(item.id, { status: 'skipped' })}>跳过此步</Button></Space>,
        ]}>
          <List.Item.Meta title={<Space wrap><Tag>{planCategory(item.category)}</Tag><Tag>{stateLabels[item.status] || '状态待核验'}</Tag>{item.title}</Space>} description={<><Typography.Paragraph>{item.description}</Typography.Paragraph><Typography.Paragraph>行动目的：{item.purpose || '未填写'}</Typography.Paragraph><Typography.Paragraph>预期产出：{item.expected_output || '未填写'}</Typography.Paragraph>{item.notes && <Typography.Paragraph>我的记录：{item.notes}</Typography.Paragraph>}</>} />
        </List.Item>} />
      </Card></List.Item>;
    }} />
    <Modal title="编辑下一步行动" open={editing !== null} onCancel={() => setEditing(null)} onOk={() => form.submit()} confirmLoading={saving} okText="保存" cancelText="取消">
      <Form form={form} layout="vertical" onFinish={(values) => { if (editing) void update(editing.id, values); }}>
        <Form.Item name="title" label="要完成的行动" rules={[{ required: true, whitespace: true, max: 240 }]}><Input maxLength={240} /></Form.Item>
        <Form.Item name="description" label="具体做法" rules={[{ required: true, whitespace: true, max: 4000 }]}><Input.TextArea maxLength={4000} /></Form.Item>
        <Form.Item name="purpose" label="行动目的"><Input.TextArea maxLength={4000} /></Form.Item>
        <Form.Item name="expected_output" label="预期产出"><Input.TextArea maxLength={4000} /></Form.Item>
        <Form.Item name="notes" label="我的记录"><Input.TextArea maxLength={4000} /></Form.Item>
      </Form>
    </Modal>
  </>;
}
