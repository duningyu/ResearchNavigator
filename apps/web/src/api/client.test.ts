import { afterEach, expect, it, vi } from 'vitest';
import { apiDownload, apiRequest } from './client';

afterEach(() => vi.unstubAllGlobals());
it('展示服务端证据不足的中文原因和补充动作，不把对象字符串化', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    detail: { reason: '相关性或关键证据尚不足，已停止生成候选研究空白。',
      actions: ['补充可定位的原文证据'], reason_codes: ['INTERNAL_CODE'] },
  }), { status: 409 })));
  await expect(apiRequest('/gaps/generate', {}, null)).rejects.toThrow(
    '相关性或关键证据尚不足，已停止生成候选研究空白。 补充可定位的原文证据',
  );
});

it.each(['request', 'download'])('does not expose upstream credentials in %s errors', async (kind) => {
  const detail = '读取失败 https://example.invalid/file?X-Amz-Signature=TEST_ONLY_SIGNATURE Authorization: Bearer TEST_ONLY_TOKEN';
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 502 })));
  const operation = kind === 'request' ? apiRequest('/papers', {}, null) : apiDownload('/papers/export', 'papers.json', null);
  await expect(operation).rejects.toThrow('请求未完成，请稍后重试。');
});

it('does not display raw internal enums as user instructions', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'EXECUTOR_RESULT_LINKAGE_INVALID' }), { status: 409 })));
  await expect(apiRequest('/jobs/1', {}, null)).rejects.toThrow('请求未完成，请稍后重试。');
});
