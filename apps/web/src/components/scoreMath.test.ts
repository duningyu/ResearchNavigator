import { describe, expect, it } from 'vitest';
import { clampScore, coveragePercent } from './scoreMath';

describe('score display math', () => {
  it('clamps invalid or out-of-range scores', () => {
    expect(clampScore(-3)).toBe(0);
    expect(clampScore(103)).toBe(100);
    expect(clampScore(Number.NaN)).toBe(0);
  });

  it('renders fractional evidence coverage as percent', () => {
    expect(coveragePercent(0.625)).toBe(62.5);
  });
});
