import { Alert, Button, Card, Checkbox, Form, InputNumber, Select, Space, message } from 'antd';
import { useEffect, useState } from 'react';
import { apiRequest } from '../api/client';
import type { UserSettings } from '../types/domain';

export function SettingsPage() {
  const [form] = Form.useForm<UserSettings>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { void apiRequest<UserSettings>('/settings/me').then((value) => form.setFieldsValue(value)).catch((reason) => setError(reason instanceof Error ? reason.message : String(reason))).finally(() => setLoading(false)); }, []);
  const save = async (values: UserSettings) => { setError(null); try { const saved = await apiRequest<UserSettings>('/settings/me', { method: 'PUT', body: JSON.stringify(values) }); form.setFieldsValue(saved); message.success('个人设置已保存'); } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); } };
  return <Space orientation="vertical" size="large" style={{ width: '100%' }}><Alert type="info" showIcon title="浏览器不接收 API Key 或模型密钥" description="此页只保存用户级偏好；真正的服务端密钥仍由部署环境管理。" />{error && <Alert type="error" showIcon title="设置操作失败" description={error} />}<Card title="研究工作流偏好" loading={loading}><Form form={form} layout="vertical" onFinish={(values) => void save(values)}><Form.Item name="default_result_count" label="默认搜索结果数" rules={[{ required: true }]}><Select options={[10,20,50].map((value) => ({ value, label: `Top ${value}` }))} /></Form.Item><Form.Item name="default_page_size" label="每页展示数量"><InputNumber min={5} max={50} /></Form.Item><Form.Item name="preferred_sources" label="偏好数据源"><Select mode="multiple" options={['fixture','openalex','crossref','arxiv','semantic_scholar'].map((value) => ({ value }))} /></Form.Item><Form.Item name="default_open_access_only" valuePropName="checked"><Checkbox>默认仅开放全文</Checkbox></Form.Item><Form.Item name="display_language" label="界面/分析语言"><Select options={[{ value: 'zh-CN', label: '简体中文' }, { value: 'en', label: 'English' }]} /></Form.Item><Form.Item name="analysis_execution_preference" label="分析执行方式"><Select options={[{ value: 'synchronous', label: '同步：直接等待结果' }, { value: 'queued', label: '队列：交给 Worker' }]} /></Form.Item><Button type="primary" htmlType="submit">保存设置</Button></Form></Card></Space>;
}
