const RUNTIME_BACKEND_PARAM = 'rn_backend';
const RUNTIME_BACKEND_STORAGE_KEY = 'rn_backend_origin';

function isAllowedOrigin(value: string): boolean {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return false;
  }
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/') return false;
  if (url.protocol === 'https:' && url.hostname.endsWith('.trycloudflare.com')) return true;
  const isLocalhost = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  return isLocalhost && (url.protocol === 'http:' || url.protocol === 'https:');
}

function normalizeOrigin(value: string): string {
  return value.replace(/\/$/, '');
}

export function getRuntimeBackendOrigin(): string | null {
  if (typeof window === 'undefined') return null;
  const candidate = new URLSearchParams(window.location.search).get(RUNTIME_BACKEND_PARAM);
  if (candidate && isAllowedOrigin(candidate)) {
    const origin = normalizeOrigin(candidate);
    window.sessionStorage.setItem(RUNTIME_BACKEND_STORAGE_KEY, origin);
    return origin;
  }
  const stored = window.sessionStorage.getItem(RUNTIME_BACKEND_STORAGE_KEY);
  return stored && isAllowedOrigin(stored) ? normalizeOrigin(stored) : null;
}

export function getApiBaseUrl(): string {
  const runtimeOrigin = getRuntimeBackendOrigin();
  if (runtimeOrigin) return `${runtimeOrigin}/api`;
  return (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, '');
}

export { isAllowedOrigin };
