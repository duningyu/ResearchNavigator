import { Button, Card, Space, Spin, Tag, Typography } from 'antd';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  clearRuntimeBackendOrigin,
  getApiBaseUrl,
  getRuntimeBackendOrigin,
  hasConfiguredBackend,
  hasInvalidRuntimeBackendParam,
  shouldUsePublicDemoBackendGate,
} from '../lib/runtimeBackend';

type BackendState =
  | 'BACKEND_NOT_CONFIGURED'
  | 'BACKEND_CONNECTING'
  | 'BACKEND_ONLINE'
  | 'BACKEND_OFFLINE'
  | 'BACKEND_UNAUTHORIZED'
  | 'BACKEND_ERROR';

type Props = {
  children: ReactNode;
  forcePublicDemo?: boolean;
};

export function BackendAvailabilityGate({ children, forcePublicDemo = false }: Props) {
  const managed = forcePublicDemo || shouldUsePublicDemoBackendGate();
  const [invalidBackend, setInvalidBackend] = useState(() => hasInvalidRuntimeBackendParam());
  const [state, setState] = useState<BackendState>(() => {
    if (!managed) return 'BACKEND_ONLINE';
    return hasConfiguredBackend() ? 'BACKEND_CONNECTING' : 'BACKEND_NOT_CONFIGURED';
  });

  const checkBackend = useCallback(async () => {
    const invalid = hasInvalidRuntimeBackendParam();
    setInvalidBackend(invalid);
    if (invalid || !hasConfiguredBackend()) {
      setState('BACKEND_NOT_CONFIGURED');
      return;
    }
    setState('BACKEND_CONNECTING');
    try {
      const response = await fetch(`${getApiBaseUrl()}/health`, {
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(8_000),
      });
      if (response.ok) setState('BACKEND_ONLINE');
      else if (response.status === 401 || response.status === 403) setState('BACKEND_UNAUTHORIZED');
      else setState('BACKEND_ERROR');
    } catch (reason) {
      setState(reason instanceof TypeError ? 'BACKEND_OFFLINE' : 'BACKEND_ERROR');
    }
  }, []);

  useEffect(() => {
    if (managed) void checkBackend();
  }, [checkBackend, managed]);

  useEffect(() => {
    if (!managed || state !== 'BACKEND_ONLINE') return undefined;
    const timer = window.setInterval(() => void checkBackend(), 15_000);
    return () => window.clearInterval(timer);
  }, [checkBackend, managed, state]);

  if (!managed || state === 'BACKEND_ONLINE') return children;

  const connecting = state === 'BACKEND_CONNECTING';
  const message = invalidBackend
    ? '提供的演示后端地址无效，已拒绝连接。'
    : state === 'BACKEND_NOT_CONFIGURED'
      ? '公网演示后端当前未启动，请稍后重试或联系项目作者。'
      : state === 'BACKEND_UNAUTHORIZED'
        ? '演示后端拒绝了健康检查，请联系项目作者。'
        : state === 'BACKEND_ERROR'
          ? '演示后端返回异常状态，请稍后重试。'
          : '公网演示后端暂时无法连接，请稍后重试。';

  const clearBackend = () => {
    clearRuntimeBackendOrigin();
    setInvalidBackend(false);
    setState('BACKEND_NOT_CONFIGURED');
  };

  return (
    <main className="backend-state-wrap">
      <Card className="backend-state-card" variant="borderless">
        <Space orientation="vertical" size="large" style={{ width: '100%' }}>
          <Tag color={connecting ? 'processing' : 'default'} data-testid="backend-status">
            {state}
          </Tag>
          <div>
            <Typography.Title level={2}>ResearchNavigator 演示当前离线</Typography.Title>
            <Typography.Paragraph type="secondary">{message}</Typography.Paragraph>
          </div>
          {connecting ? (
            <Space><Spin size="small" /><Typography.Text>正在连接演示后端…</Typography.Text></Space>
          ) : (
            <Space wrap>
              {hasConfiguredBackend() && <Button type="primary" onClick={() => void checkBackend()}>重试连接</Button>}
              {(getRuntimeBackendOrigin() || invalidBackend) && (
                <Button onClick={clearBackend}>清除过期后端地址</Button>
              )}
            </Space>
          )}
          <Typography.Text className="backend-state-note">
            前端展示页保持在线；研究数据与后台服务仅在受监督演示启动后可用。
          </Typography.Text>
        </Space>
      </Card>
    </main>
  );
}
