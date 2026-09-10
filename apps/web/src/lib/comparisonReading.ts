import type { ComparisonRun } from '../types/domain';

/** Reading triage only. Never compare numerical results across unknown protocols. */
export function readingOrder(comparison: ComparisonRun) {
  const scores = comparison.papers.map((paper) => ({ paper, coverage: comparison.rows.filter((row) =>
    ['research_problem', 'task_definition', 'major_results', 'limitations_author_stated', 'future_work_explicit'].includes(row.key)
    && row.cells.some((cell) => cell.paper_id === paper.id && cell.evidence_state === 'evidenced'
      && cell.value != null && cell.citations.some((citation) => Boolean(citation.source_type && citation.supporting_text))),
  ).length }));
  const eligible = scores.filter((row) => row.paper.relation === 'direct');
  const max = Math.max(0, ...eligible.map((row) => row.coverage));
  const priority = eligible.filter((row) => max > 0 && row.coverage === max).map((row) => row.paper);
  return {
    priority,
    others: scores.filter((row) => !priority.some((paper) => paper.id === row.paper.id)).map((row) => row.paper),
    reason: !max ? '暂不能推荐先读顺序：方向相关性或可定位原文尚不足，请先核对任务并补充材料。'
      : `${priority.length > 1 ? '并列优先核读' : '优先核读'}：这些论文在任务、结果或局限上有更多可定位依据；这不是质量排名，也不代表与你的方向更相关。`,
  };
}
