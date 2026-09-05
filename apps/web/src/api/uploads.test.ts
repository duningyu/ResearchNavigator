import { afterEach, describe, expect, it, vi } from 'vitest';
import { uploadPdfDirect } from './uploads';

afterEach(() => vi.restoreAllMocks());

describe('uploadPdfDirect', () => {
  it('sends metadata to the API and bytes directly to the presigned R2 URL', async () => {
    const file = new File([new Uint8Array([37, 80, 68, 70, 45, 49])], 'fixture.pdf', { type: 'application/pdf' });
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({
        upload_method: 'PUT',
        presigned_url: 'https://r2.example.invalid/signed-upload',
        required_headers: { 'Content-Type': 'application/pdf', 'x-amz-meta-sha256': 'fixture-hash' },
        completion_token: 'opaque-completion-token',
        expires_at: '2099-01-01T00:00:00Z',
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 7 }), { status: 200 }));

    await uploadPdfDirect('7', file);

    expect(fetchMock).toHaveBeenCalledTimes(3);
    const [presignUrl, presignOptions] = fetchMock.mock.calls[0];
    expect(String(presignUrl)).toContain('/papers/7/uploads/presign');
    expect(presignOptions?.method).toBe('POST');
    expect(JSON.parse(String(presignOptions?.body))).toMatchObject({
      filename: 'fixture.pdf',
      content_type: 'application/pdf',
      size_bytes: file.size,
    });

    const [r2Url, r2Options] = fetchMock.mock.calls[1];
    expect(r2Url).toBe('https://r2.example.invalid/signed-upload');
    expect(r2Options?.method).toBe('PUT');
    expect(new Headers(r2Options?.headers).get('Content-Type')).toBe('application/pdf');
    expect(new Headers(r2Options?.headers).get('x-amz-meta-sha256')).toBe('fixture-hash');
    expect(r2Options?.body).toBe(file);

    const [finalizeUrl, finalizeOptions] = fetchMock.mock.calls[2];
    expect(String(finalizeUrl)).toContain('/papers/7/uploads/finalize');
    expect(JSON.parse(String(finalizeOptions?.body))).toEqual({ completion_token: 'opaque-completion-token' });
  });
});
