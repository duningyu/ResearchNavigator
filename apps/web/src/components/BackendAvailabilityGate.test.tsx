import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BackendAvailabilityGate } from './BackendAvailabilityGate';


function response(status: number): Response {
  return new Response(status === 200 ? JSON.stringify({ status: 'ok' }) : '', {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}


beforeEach(() => {
  window.history.replaceState({}, '', '/');
  window.sessionStorage.clear();
  vi.restoreAllMocks();
});


afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});


describe('public demo backend availability gate', () => {
  it('shows a polished not-configured state without requesting the naked public origin', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<BackendAvailabilityGate forcePublicDemo><div>workspace</div></BackendAvailabilityGate>);

    expect(screen.getByTestId('backend-status')).toHaveTextContent('BACKEND_NOT_CONFIGURED');
    expect(screen.getByText('ResearchNavigator 演示当前离线')).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('classifies an unreachable stored tunnel as offline', async () => {
    window.sessionStorage.setItem('rn_backend_origin', 'https://expired.trycloudflare.com');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    render(<BackendAvailabilityGate forcePublicDemo><div>workspace</div></BackendAvailabilityGate>);

    await waitFor(() => expect(screen.getByTestId('backend-status')).toHaveTextContent('BACKEND_OFFLINE'));
    expect(screen.getByRole('button', { name: '清除过期后端地址' })).toBeVisible();
  });

  it('distinguishes backend HTTP errors and unauthorized responses', async () => {
    window.sessionStorage.setItem('rn_backend_origin', 'https://demo.trycloudflare.com');
    const fetchMock = vi.fn().mockResolvedValueOnce(response(503)).mockResolvedValueOnce(response(401));
    vi.stubGlobal('fetch', fetchMock);
    const view = render(<BackendAvailabilityGate forcePublicDemo><div>workspace</div></BackendAvailabilityGate>);

    await waitFor(() => expect(screen.getByTestId('backend-status')).toHaveTextContent('BACKEND_ERROR'));
    view.unmount();
    render(<BackendAvailabilityGate forcePublicDemo><div>workspace</div></BackendAvailabilityGate>);
    await waitFor(() => expect(screen.getByTestId('backend-status')).toHaveTextContent('BACKEND_UNAUTHORIZED'));
  });

  it('renders the application after a healthy backend response', async () => {
    window.sessionStorage.setItem('rn_backend_origin', 'https://demo.trycloudflare.com');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200)));
    render(<BackendAvailabilityGate forcePublicDemo><div>workspace</div></BackendAvailabilityGate>);

    await waitFor(() => expect(screen.getByText('workspace')).toBeVisible());
  });

  it('moves an already-open workspace offline when a later health poll fails', async () => {
    vi.useFakeTimers();
    window.sessionStorage.setItem('rn_backend_origin', 'https://demo.trycloudflare.com');
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(200))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'));
    vi.stubGlobal('fetch', fetchMock);
    render(<BackendAvailabilityGate forcePublicDemo><div>workspace</div></BackendAvailabilityGate>);

    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText('workspace')).toBeVisible();
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
    expect(screen.getByTestId('backend-status')).toHaveTextContent('BACKEND_OFFLINE');
    vi.useRealTimers();
  });

  it('rejects an invalid backend hostname without making a request', () => {
    window.history.replaceState({}, '', '/?rn_backend=https%3A%2F%2Fevil.example');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<BackendAvailabilityGate forcePublicDemo><div>workspace</div></BackendAvailabilityGate>);

    expect(screen.getByTestId('backend-status')).toHaveTextContent('BACKEND_NOT_CONFIGURED');
    expect(screen.getByText(/后端地址无效/)).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('recovers when retry reaches a healthy backend', async () => {
    window.sessionStorage.setItem('rn_backend_origin', 'https://demo.trycloudflare.com');
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(response(200));
    vi.stubGlobal('fetch', fetchMock);
    render(<BackendAvailabilityGate forcePublicDemo><div>workspace</div></BackendAvailabilityGate>);

    await waitFor(() => expect(screen.getByTestId('backend-status')).toHaveTextContent('BACKEND_OFFLINE'));
    fireEvent.click(screen.getByRole('button', { name: '重试连接' }));
    await waitFor(() => expect(screen.getByText('workspace')).toBeVisible());
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('clears an expired tunnel and returns to the not-configured state', async () => {
    window.history.replaceState({}, '', '/?rn_backend=https%3A%2F%2Fexpired.trycloudflare.com');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    render(<BackendAvailabilityGate forcePublicDemo><div>workspace</div></BackendAvailabilityGate>);

    await waitFor(() => expect(screen.getByTestId('backend-status')).toHaveTextContent('BACKEND_OFFLINE'));
    fireEvent.click(screen.getByRole('button', { name: '清除过期后端地址' }));
    expect(window.sessionStorage.getItem('rn_backend_origin')).toBeNull();
    expect(window.location.search).toBe('');
    expect(screen.getByTestId('backend-status')).toHaveTextContent('BACKEND_NOT_CONFIGURED');
  });
});
