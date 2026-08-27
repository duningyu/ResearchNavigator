import { Alert, Button, Card, Form, Input, Select, message } from 'antd';
import { useEffect } from 'react';
import { apiRequest } from '../api/client';

type ProfileForm = { stage?: string; major?: string; broad_direction?: string; keywords?: string[]; excluded_terms?: string[]; preferences?: string[]; compute_constraints?: string };

export function ProfilePage() {
  const [form] = Form.useForm<ProfileForm>();
  useEffect(() => { void apiRequest<ProfileForm | null>('/research-profiles/me').then((value) => value && form.setFieldsValue(value)); }, [form]);
  const save = async (values: ProfileForm) => { await apiRequest('/research-profiles/me', { method: 'PUT', body: JSON.stringify({ ...values, keywords: values.keywords ?? [], excluded_terms: values.excluded_terms ?? [], preferences: values.preferences ?? [] }) }); message.success('研究档案已保存'); };
  return <Card title="研究方向档案"><Alert style={{ marginBottom: 16 }} type="warning" message="所有系统推断均应允许人工修改；不要把导师给出的宽泛方向当作已确认研究问题。" /><Form form={form} layout="vertical" onFinish={(values) => void save(values)}><Form.Item name="stage" label="研究阶段"><Select options={['硕士一年级','硕士二年级','博士','转方向','其他'].map((value) => ({ value }))} /></Form.Item><Form.Item name="major" label="专业"><Input /></Form.Item><Form.Item name="broad_direction" label="宽泛研究方向"><Input /></Form.Item><Form.Item name="keywords" label="关键词"><Select mode="tags" /></Form.Item><Form.Item name="excluded_terms" label="排除词"><Select mode="tags" /></Form.Item><Form.Item name="preferences" label="偏好"><Select mode="tags" options={['理论研究','方法研究','工程应用','数据研究','复现优先','发表优先'].map((value) => ({ value }))} /></Form.Item><Form.Item name="compute_constraints" label="算力与时间约束"><Input.TextArea rows={3} /></Form.Item><Button type="primary" htmlType="submit">保存档案</Button></Form></Card>;
}
