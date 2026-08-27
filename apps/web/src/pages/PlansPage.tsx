import { Button, Card, List, Progress, Space, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { apiRequest } from '../api/client';
import type { ResearchPlan } from '../types/domain';

export function PlansPage() {
  const [plans, setPlans] = useState<ResearchPlan[]>([]);
  const load = () => void apiRequest<ResearchPlan[]>('/plans').then(setPlans);
  useEffect(load, []);
  const complete = async (id: number) => { await apiRequest(`/plan-items/${id}`, { method: 'PUT', body: JSON.stringify({ status: 'done' }) }); message.success('计划项已完成'); load(); };
  return <List dataSource={plans} locale={{ emptyText: '请先完成候选空白的反证检索和人工确认，再创建研究计划。' }} renderItem={(plan) => { const done = plan.items.filter((item) => item.status === 'done').length; return <List.Item><Card style={{ width: '100%' }} title={plan.title}><Typography.Paragraph>{plan.objective}</Typography.Paragraph><Progress percent={plan.items.length ? Math.round(done / plan.items.length * 100) : 0} /><List dataSource={plan.items} renderItem={(item) => <List.Item actions={[item.status !== 'done' ? <Button key="done" onClick={() => void complete(item.id)}>完成</Button> : null]}><List.Item.Meta title={<Space><Tag>{item.category}</Tag>{item.title}</Space>} description={item.description} /></List.Item>} /></Card></List.Item>; }} />;
}
