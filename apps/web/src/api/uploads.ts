import { apiRequest, ApiError } from './client';

export interface PresignUploadResponse {
  upload_method: 'PUT';
  presigned_url: string;
  required_headers: Record<string, string>;
  completion_token: string;
  expires_at: string;
}

function sha256Hex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function readFileBytes(file: File): Promise<ArrayBuffer> {
  if (typeof file.arrayBuffer === 'function') return file.arrayBuffer();
  return new Promise<ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error('Unable to read upload file'));
    reader.onload = () => {
      if (reader.result instanceof ArrayBuffer) resolve(reader.result);
      else reject(new Error('Upload file was not read as bytes'));
    };
    reader.readAsArrayBuffer(file);
  });
}

export async function getFileSha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', await readFileBytes(file));
  return sha256Hex(digest);
}

export function shouldUseDirectUpload(): boolean {
  return import.meta.env.VITE_DIRECT_UPLOAD === 'true';
}

export async function uploadPdfDirect(paperId: string, file: File): Promise<unknown> {
  const sha256 = await getFileSha256(file);
  const presign = await apiRequest<PresignUploadResponse>(`/papers/${paperId}/uploads/presign`, {
    method: 'POST',
    body: JSON.stringify({
      filename: file.name,
      content_type: file.type || 'application/pdf',
      size_bytes: file.size,
      sha256,
    }),
  });

  const uploadResponse = await fetch(presign.presigned_url, {
    method: presign.upload_method,
    headers: presign.required_headers,
    body: file,
  });
  if (!uploadResponse.ok) {
    throw new ApiError(uploadResponse.status, 'Direct PDF upload failed');
  }

  return apiRequest(`/papers/${paperId}/uploads/finalize`, {
    method: 'POST',
    body: JSON.stringify({ completion_token: presign.completion_token }),
  });
}
