import { Alert, Button, Card, List, Space, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { apiRequest } from '../api/client';
import type { SourceStatus } from '../types/domain';

export function SourcesPage() {
  const [sources, setSources] = useState<SourceStatus[]>([]);
  const [testing, setTesting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => void apiRequest<SourceStatus[]>('/sources/status').then(setSources).catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  useEffect(load, []);
  const test = async (name: string) => { setTesting(name); setError(null); try { const result = await apiRequest<SourceStatus>(`/sources/${name}/test`, { method: 'POST' }); setSources((items) => items.map((item) => item.name === name ? result : item)); message.success(`${name} 主动测试完成：${result.status}`); } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); } finally { setTesting(null); } };
  return <Space orientation="vertical" size="large" style={{ width: '100%' }}><Alert type="info" showIcon title="真实来源冒烟与确定性 fixture 回归分开验收" description="真实 OpenAlex/arXiv 等结果会变化；主动测试只验证当前连接状态。正式验收还记录查询、时间、状态、稳定标识符与原始响应哈希。" />{error && <Alert type="error" showIcon title="来源测试失败" description={error} />}<Card title="数据源状态"><List dataSource={sources} renderItem={(source) => <List.Item actions={[<Button key="test" loading={testing === source.name} onClick={() => void test(source.name ?? '')}>连通性测试</Button>]}><List.Item.Meta title={<Space><Typography.Text strong>{source.name}</Typography.Text><Tag color={source.status === 'ok' ? 'green' : source.status === 'error' ? 'red' : 'default'}>{source.status}</Tag></Space>} description={`${source.detail ?? ''} · enabled=${String(source.enabled)} · configured=${String(source.configured)} · checked=${source.checked_at ?? '未知'}`} /></List.Item>} /></Card></Space>;
}
