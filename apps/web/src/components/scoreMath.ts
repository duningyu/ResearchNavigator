export function clampScore(score: number | null): number {
  if (score === null || !Number.isFinite(score)) return 0;
  return Math.round(Math.max(0, Math.min(100, score)) * 100) / 100;
}

export function coveragePercent(coverage: number | null): number | null {
  if (coverage === null) return null;
  return clampScore(coverage <= 1 ? coverage * 100 : coverage);
}
