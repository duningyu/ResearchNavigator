import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { PaperPage } from './PaperPage';

vi.mock('../components/PaperIntelligenceCards', () => ({ PaperIntelligenceCards: () => null }));
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it('locates a cited abstract only when its exact excerpt still exists in the current paper', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith('/papers/42')) return new Response(JSON.stringify({ id: 42, title: 'Cited paper', authors: [], source_urls: [], abstract: 'Context. Future work needs replication.', abstract_evidence_verified: true }));
    if (path.includes('/analysis')) return new Response('{}', { status: 404 });
    return new Response('[]');
  });
  render(<MemoryRouter initialEntries={['/papers/42?project=7&evidenceSource=abstract&quote=Future%20work%20needs%20replication.']}><Routes><Route path='/papers/:paperId' element={<PaperPage />} /></Routes></MemoryRouter>);
  const evidence = await screen.findByRole('region', { name: '已定位的原文依据' });
  expect(evidence).toHaveTextContent('Future work needs replication.');
  expect(fetcher.mock.calls.some(([input]) => String(input).endsWith('/analysis?project_id=7'))).toBe(true);
});
it('does not promote a stale or fabricated citation URL to verified evidence', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith('/papers/42')) return new Response(JSON.stringify({ id: 42, title: 'Changed paper', authors: [], source_urls: [], abstract: 'Different material.', abstract_evidence_verified: true }));
    if (path.includes('/analysis')) return new Response('{}', { status: 404 });
    return new Response('[]');
  });
  render(<MemoryRouter initialEntries={['/papers/42?evidenceSource=abstract&quote=Unsupported%20claim']}><Routes><Route path='/papers/:paperId' element={<PaperPage />} /></Routes></MemoryRouter>);
  expect(await screen.findByText('未找到对应原文片段，材料可能已更新；请重新核对引用。')).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: '已定位的原文依据' })).not.toBeInTheDocument();
});
it('blocks duplicate creation when existing workflow restoration fails', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith('/papers/42')) return new Response(JSON.stringify({ id: 42, title: 'Restore failure', authors: [], source_urls: [] }));
    if (path.endsWith('/evidence-workflows')) return new Response('{}', { status: 503 });
    if (path.endsWith('/analysis')) return new Response('{}', { status: 404 });
    return new Response('[]');
  });
  render(<MemoryRouter initialEntries={['/papers/42']}><Routes><Route path='/papers/:paperId' element={<PaperPage />} /></Routes></MemoryRouter>);
  await screen.findByText('暂时无法恢复材料获取进展，请刷新后再试，避免重复提交。');
  expect(screen.getByRole('button', { name: '获取公开材料并分析' })).toBeDisabled();
});

it('does not apply a late write response after navigating to another paper', async () => {
  let finish!: (response: Response) => void;
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith('/acquire-evidence')) return new Promise<Response>((resolve) => { finish = resolve; });
    if (/\/papers\/4[23]$/.test(path)) return new Response(JSON.stringify({ id: Number(path.slice(-2)), title: path.endsWith('42') ? 'First paper' : 'Second paper', authors: [], source_urls: [], abstract_evidence_verified: false }));
    if (path.endsWith('/analysis')) return new Response('{}', { status: 404 });
    return new Response('[]');
  });
  render(<MemoryRouter initialEntries={['/papers/42']}><Link to='/papers/43'>下一篇</Link><Routes><Route path='/papers/:paperId' element={<PaperPage />} /></Routes></MemoryRouter>);
  await screen.findByText('First paper');
  fireEvent.click(screen.getByRole('button', { name: '获取更多证据并重新分析' }));
  fireEvent.click(screen.getByRole('link', { name: '下一篇' }));
  await screen.findByText('Second paper');
  finish(new Response(JSON.stringify({ paper: { id: 42, title: 'Stale first result', authors: [], source_urls: [] }, analysis: null, outcome: 'source_unavailable', source_status: {} })));
  await waitFor(() => expect(screen.queryByText('Stale first result')).not.toBeInTheDocument());
  expect(screen.getByText('Second paper')).toBeInTheDocument();
});
it('restores saved contextual progress without creating or running another workflow', async () => {
  const writes: string[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input);
    if (init?.method && init.method !== 'GET') writes.push(path);
    let data: unknown = [];
    if (path.endsWith('/papers/42')) data = { id: 42, title: 'Restored paper', authors: [], source_urls: [], abstract_evidence_verified: true };
    if (path.endsWith('/analysis')) return new Response('{}', { status: 404 });
    if (path.endsWith('/evidence-workflows')) data = [{ id: 8, paper_id: 42, project_id: null, status: 'partial', terminal: true, result: {}, events: [], strongest_evidence: 'abstract_only' }];
    return new Response(JSON.stringify(data));
  });
  render(<MemoryRouter initialEntries={['/papers/42']}><Routes><Route path='/papers/:paperId' element={<PaperPage />} /></Routes></MemoryRouter>);
  await screen.findByText('Restored paper');
  await screen.findByText('本次处理已结束');
  expect(writes).toEqual([]);
});

it('acquires public evidence through the existing create and run seam without bypassing licence confirmation', async () => {
  const calls: Array<{ path: string; body: unknown }> = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input);
    calls.push({ path, body: init?.body ? JSON.parse(String(init.body)) : null });
    let data: unknown = [];
    if (path.endsWith('/papers/42')) data = { id: 42, title: 'Original English Paper', authors: [], source_urls: [], abstract: 'Original abstract', abstract_evidence_verified: true };
    if (path.endsWith('/analysis')) return new Response('{}', { status: 404 });
    if (path.endsWith('/evidence-workflows') && init?.method === 'POST') data = { id: 8, paper_id: 42, project_id: null, status: 'pending', terminal: false, result: {}, events: [], strongest_evidence: 'abstract_only' };
    if (path.endsWith('/run')) data = { id: 8, status: 'partial', terminal: true, result: {}, events: [], strongest_evidence: 'abstract_only' };
    return new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } });
  });
  render(<MemoryRouter initialEntries={['/papers/42']}><Routes><Route path='/papers/:paperId' element={<PaperPage />} /></Routes></MemoryRouter>);
  await screen.findByText('Original English Paper');
  fireEvent.click(screen.getByRole('button', { name: '获取公开材料并分析' }));
  await waitFor(() => expect(calls.some((call) => call.path.endsWith('/evidence-workflows/8/run'))).toBe(true));
  const creation = calls.find((call) => call.path.endsWith('/papers/42/evidence-workflows') && call.body);
  expect(creation?.body).toMatchObject({ allow_oa_fulltext: true, confirm_limited_license: false });
  expect(screen.getByRole('button', { name: '上传并重新分析' })).toBeDisabled();
  expect(document.body.textContent).not.toContain('abstract_only');
});
