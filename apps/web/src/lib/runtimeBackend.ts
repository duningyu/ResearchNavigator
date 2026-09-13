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

export function hasInvalidRuntimeBackendParam(): boolean {
  if (typeof window === 'undefined') return false;
  const candidate = new URLSearchParams(window.location.search).get(RUNTIME_BACKEND_PARAM);
  return candidate !== null && !isAllowedOrigin(candidate);
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

export function hasConfiguredBackend(): boolean {
  if (hasInvalidRuntimeBackendParam()) return false;
  if (getRuntimeBackendOrigin()) return true;
  return Boolean(import.meta.env.VITE_API_BASE_URL?.trim()) || getApiBaseUrl() === '/api';
}

export function clearRuntimeBackendOrigin(): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.removeItem(RUNTIME_BACKEND_STORAGE_KEY);
  const url = new URL(window.location.href);
  url.searchParams.delete(RUNTIME_BACKEND_PARAM);
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
}

export function shouldUsePublicDemoBackendGate(): boolean {
  if (typeof window === 'undefined') return false;
  if (new URLSearchParams(window.location.search).has(RUNTIME_BACKEND_PARAM)) return true;
  if (window.sessionStorage.getItem(RUNTIME_BACKEND_STORAGE_KEY)) return true;
  return !['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname);
}

export { isAllowedOrigin };
