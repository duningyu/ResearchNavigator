import { Alert, Button, Card, Descriptions, List, Space, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { apiRequest } from '../api/client';
import type { Job } from '../types/domain';

export function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = () => void apiRequest<Job[]>('/jobs').then(setJobs).catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  useEffect(load, []);
  const create = async () => { await apiRequest<Job>('/jobs', { method: 'POST', body: JSON.stringify({ job_type: 'noop', payload: { source: 'web-smoke' } }) }); message.success('任务已创建；pending 不是验收通过，需等待 terminal 状态'); load(); };
  const cancel = async (job: Job) => { await apiRequest<Job>(`/jobs/${job.id}/cancel`, { method: 'POST' }); message.success('任务已取消'); load(); };
  return <Space orientation="vertical" size="large" style={{ width: '100%' }}><Alert type="info" showIcon title="Worker 验收采用 terminal 状态" description="只有 succeeded / failed / cancelled 才是完成状态；合法 pending 只能证明任务入队，不能证明 worker 正常。" />{error && <Alert type="error" showIcon title="任务读取失败" description={error} />}<Space><Button type="primary" onClick={() => void create()}>创建 No-op 验证任务</Button><Button onClick={load}>刷新全部任务</Button></Space><List dataSource={jobs} locale={{ emptyText: '暂无任务' }} renderItem={(job) => <List.Item><Card style={{ width: '100%' }} title={<Space><Typography.Text strong>#{job.id} · {job.job_type}</Typography.Text><Tag color={job.terminal ? 'green' : 'blue'}>{job.status}</Tag></Space>} extra={!job.terminal && <Button danger onClick={() => void cancel(job)}>取消任务</Button>}><Descriptions column={{ xs: 1, md: 2 }} size="small"><Descriptions.Item label="terminal">{String(job.terminal)}</Descriptions.Item><Descriptions.Item label="attempts">{job.attempt_count}/{job.max_attempts}</Descriptions.Item><Descriptions.Item label="started">{job.started_at ?? '未开始'}</Descriptions.Item><Descriptions.Item label="finished">{job.finished_at ?? job.cancelled_at ?? '未完成'}</Descriptions.Item><Descriptions.Item label="result"><pre className="inline-json">{JSON.stringify(job.result, null, 2)}</pre></Descriptions.Item><Descriptions.Item label="error">{job.error ?? '无'}</Descriptions.Item></Descriptions></Card></List.Item>} /></Space>;
}
