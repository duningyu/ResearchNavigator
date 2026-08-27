export function clampScore(score: number): number {
  if (!Number.isFinite(score)) return 0;
  return Math.round(Math.max(0, Math.min(100, score)) * 100) / 100;
}

export function coveragePercent(coverage: number): number {
  return clampScore(coverage <= 1 ? coverage * 100 : coverage);
}
