import { getApiBaseUrl } from '../lib/runtimeBackend';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
  }
}

function safeInstruction(value: unknown): value is string {
  return typeof value === 'string' && value.length <= 500 && /[\u4e00-\u9fff]/u.test(value)
    && !/(https?:|authorization|bearer|cookie|token|secret|credential|signature|[<>{}]|[A-Z]{2,}_[A-Z_]+|[A-Z]:\\)/i.test(value);
}

function displayError(value: unknown, status: number): string {
  if (safeInstruction(value)) return value;
  if (typeof value === 'object' && value !== null && 'reason' in value
      && safeInstruction(value.reason)) {
    const actions = 'actions' in value && Array.isArray(value.actions)
      ? value.actions.filter(safeInstruction) : [];
    return [value.reason, ...actions].join(' ');
  }
  if (status === 401) return '登录已过期，请重新登录。';
  if (status === 403) return '当前账号无权执行此操作。';
  if (status === 422) return '提交的信息不完整或格式不正确，请检查后重试。';
  return '请求未完成，请稍后重试。';
}

export function getStoredToken(): string | null {
  return localStorage.getItem('rn_access_token');
}

export function setStoredToken(token: string | null): void {
  if (token) localStorage.setItem('rn_access_token', token);
  else localStorage.removeItem('rn_access_token');
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  token: string | null = getStoredToken(),
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${getApiBaseUrl()}${path}`, { ...options, headers });
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }
  if (!response.ok) {
    const detail =
      typeof payload === 'object' && payload !== null && 'detail' in payload
        ? displayError((payload as { detail: unknown }).detail, response.status)
        : displayError(null, response.status);
    throw new ApiError(response.status, detail);
  }
  return payload as T;
}

export async function apiDownload(path: string, filename: string, token: string | null = getStoredToken()): Promise<void> {
  const headers = new Headers();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${getApiBaseUrl()}${path}`, { headers });
  if (!response.ok) {
    // Never render raw download responses: proxies may include signed URLs or HTML.
    throw new ApiError(response.status, displayError(null, response.status));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
