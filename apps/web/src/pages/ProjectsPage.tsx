import { Button, Card, Form, Input, List, Modal, Space, Tag, message } from 'antd';
import { useEffect, useState } from 'react';
import { apiRequest } from '../api/client';
import type { Project } from '../types/domain';

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [open, setOpen] = useState(false);
  const load = () => void apiRequest<Project[]>('/projects').then(setProjects);
  useEffect(load, []);
  const create = async (values: Partial<Project>) => { await apiRequest('/projects', { method: 'POST', body: JSON.stringify(values) }); setOpen(false); message.success('项目已创建'); load(); };
  return <Space direction="vertical" size="large" style={{ width: '100%' }}><Button type="primary" onClick={() => setOpen(true)}>新建研究项目</Button><List grid={{ gutter: 16, xs: 1, md: 2, xl: 3 }} dataSource={projects} locale={{ emptyText: '尚无研究项目' }} renderItem={(project) => <List.Item><Card title={project.name} extra={<Tag>{project.status}</Tag>}><p>{project.broad_direction}</p><p>{project.description}</p></Card></List.Item>} /><Modal title="新建研究项目" open={open} footer={null} onCancel={() => setOpen(false)}><Form layout="vertical" onFinish={(values) => void create(values)}><Form.Item name="name" label="项目名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="broad_direction" label="研究方向"><Input /></Form.Item><Form.Item name="description" label="说明"><Input.TextArea /></Form.Item><Button type="primary" htmlType="submit">创建</Button></Form></Modal></Space>;
}
