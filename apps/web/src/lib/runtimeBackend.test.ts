import { afterEach, describe, expect, it } from 'vitest';
import { getApiBaseUrl, getRuntimeBackendOrigin, isAllowedOrigin } from './runtimeBackend';

afterEach(() => {
  window.history.replaceState({}, '', '/');
  window.sessionStorage.clear();
});

describe('runtime backend origin', () => {
  it('accepts a TryCloudflare HTTPS origin', () => {
    expect(isAllowedOrigin('https://demo.trycloudflare.com/')).toBe(true);
  });

  it('accepts localhost origins for development', () => {
    expect(isAllowedOrigin('http://localhost:8000')).toBe(true);
  });

  it('rejects arbitrary public or external HTTP origins', () => {
    expect(isAllowedOrigin('https://evil.example')).toBe(false);
    expect(isAllowedOrigin('http://demo.trycloudflare.com')).toBe(false);
  });

  it('uses sessionStorage and runtime URL over build-time URL', () => {
    window.history.replaceState({}, '', '/?rn_backend=https%3A%2F%2Fdemo.trycloudflare.com');
    expect(getRuntimeBackendOrigin()).toBe('https://demo.trycloudflare.com');
    expect(window.sessionStorage.getItem('rn_backend_origin')).toBe('https://demo.trycloudflare.com');
    expect(getApiBaseUrl()).toBe('https://demo.trycloudflare.com/api');
  });

  it('rejects an invalid query override and keeps the build-time fallback', () => {
    window.history.replaceState({}, '', '/?rn_backend=https%3A%2F%2Fevil.example');
    expect(getRuntimeBackendOrigin()).toBe(null);
    expect(getApiBaseUrl()).toBe('/api');
  });
});
