import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest } from './client';

afterEach(() => vi.restoreAllMocks());

describe('apiRequest', () => {
  it('adds bearer token and parses JSON', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    await expect(apiRequest('/health', {}, 'token-1')).resolves.toEqual({ ok: true });
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(headers.get('Authorization')).toBe('Bearer token-1');
  });

  it('raises API detail for non-2xx responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'denied' }), { status: 403 }));
    await expect(apiRequest('/private', {}, 'token-1')).rejects.toEqual(new ApiError(403, 'denied'));
  });
});
