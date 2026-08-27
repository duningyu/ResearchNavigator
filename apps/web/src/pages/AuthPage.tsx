import {
  ArrowRightOutlined,
  CheckCircleFilled,
  CompassOutlined,
  FileSearchOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { Alert, Button, Card, Form, Input, Radio, Space, Tag, Typography } from 'antd';
import { useState } from 'react';
import { apiRequest } from '../api/client';
import { useAuth } from '../auth/AuthContext';

export function AuthPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [error, setError] = useState<string | null>(null);
  const { setSession } = useAuth();
  const submit = async (values: Record<string, string>) => {
    setError(null);
    try {
      const payload = await apiRequest<{
        access_token: string;
        user: { id: number; email: string; display_name: string; is_admin: boolean };
      }>(`/auth/${mode}`, { method: 'POST', body: JSON.stringify(values) }, null);
      setSession(payload.access_token, payload.user);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };
  return (
    <div className="auth-wrap">
      <section className="auth-hero" aria-label="ResearchNavigator 介绍">
        <Tag className="auth-kicker">RESEARCH NAVIGATOR · 2.1</Tag>
        <div className="auth-brand-lockup"><span className="auth-brand-mark">R</span><span>研途智选</span></div>
        <Typography.Title className="auth-title">把证据变成<br />下一步研究决策</Typography.Title>
        <Typography.Paragraph className="auth-lede">从研究档案到可执行计划，始终保留来源、边界和人工确认。</Typography.Paragraph>
        <div className="auth-proof-grid">
          <div><CompassOutlined /><span><strong>方向建档</strong>把研究约束变成可追踪的起点</span></div>
          <div><FileSearchOutlined /><span><strong>多源检索</strong>保留每一条论文证据的来源</span></div>
          <div><SafetyCertificateOutlined /><span><strong>审慎结论</strong>候选空白不等于创新性证明</span></div>
        </div>
        <div className="auth-footer-note"><CheckCircleFilled /> 本地优先 · 可审计 · 证据有界</div>
      </section>
      <section className="auth-panel">
        <Card className="auth-card" variant="borderless">
          <Space orientation="vertical" size="large" style={{ width: '100%' }}>
            <div>
              <Typography.Text className="section-eyebrow">研究者入口</Typography.Text>
              <Typography.Title level={2} className="auth-form-title">{mode === 'login' ? '继续你的研究工作流' : '创建研究工作空间'}</Typography.Title>
              <Typography.Text type="secondary">{mode === 'login' ? '登录以查看项目、论文库与证据记录。' : '用一个账户保存你的研究路径与人工判断。'}</Typography.Text>
            </div>
            <Radio.Group value={mode} onChange={(event) => setMode(event.target.value)} buttonStyle="solid">
              <Radio.Button value="login">登录</Radio.Button>
              <Radio.Button value="register">注册</Radio.Button>
            </Radio.Group>
            {error && <Alert type="error" message={error} showIcon />}
            <Form layout="vertical" onFinish={(values) => void submit(values)}>
              {mode === 'register' && <Form.Item name="display_name" label="姓名" rules={[{ required: true }]}><Input /></Form.Item>}
              <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email' }]}><Input /></Form.Item>
              <Form.Item name="password" label="密码" rules={[{ required: true, min: 12 }]}><Input.Password /></Form.Item>
              <Button type="primary" htmlType="submit" block>{mode === 'login' ? '登录' : '创建账户'}</Button>
            </Form>
            <Typography.Text type="secondary" className="auth-assurance">系统仅基于当前可访问证据生成结构化结果；请勿将候选空白视为创新性结论。</Typography.Text>
          </Space>
        </Card>
        <Typography.Text className="auth-panel-footer">ResearchNavigator <ArrowRightOutlined /> Evidence-first research workspace</Typography.Text>
      </section>
    </div>
  );
}
