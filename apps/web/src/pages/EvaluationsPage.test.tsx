import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EvaluationsPage } from './EvaluationsPage';

function json(value: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' }, ...init });
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('EvaluationsPage', () => {
  it('does not describe simulated, LLM or developer ratings as real expert validation', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/evaluations/assignments')) return json([]);
      if (url.endsWith('/evaluations/studies')) return json([]);
      return json({ detail: 'unexpected' }, { status: 500 });
    });
    render(<EvaluationsPage />);
    expect(await screen.findByText('awaiting_real_experts')).toBeInTheDocument();
    expect(screen.getAllByText(/模拟或开发者评分不能作为真实专家验证/).length).toBeGreaterThan(0);
    expect(screen.getByText(/LLM 评分也不能作为专家真值/)).toBeInTheDocument();
  });
});
