const missing = '暂无可展示的证据，请补充材料';
export const scoreLabels: Record<string, string> = {
  semantic_similarity: '词语相近程度（不等于任务相关）', task_alignment: '研究任务匹配',
  data_modality: '数据类型匹配', prediction_output: '输出目标匹配', evaluation_protocol: '评价协议',
  resource_fit: '资源条件适配', code_availability: '代码可用性', data_availability: '数据可用性',
  method_completeness: '方法材料完整性', environment_documentation: '运行环境说明',
  hyperparameter_documentation: '参数说明', compute_fit: '算力条件适配', license_clarity: '许可清晰度',
};
const states: Record<string, string> = {
  generated: '待核实的研究机会', pending_confirmation: '等待你审阅', confirmed: '已人工确认',
  challenged: '反证检索已完成', rejected: '暂不采用', challenging: '正在查找相近研究',
  evidenced: '有材料支持', insufficient_evidence: '证据不足', unknown: '尚不明确',
  metadata_only: '仅书目信息', abstract_only: '仅摘要', open_fulltext: '已获取公开正文',
  partial_fulltext: '仅部分正文可读取，不能代表完整论文',
  user_uploaded_fulltext: '用户提供正文', publisher_authorized_fulltext: '已授权正文',
  pending: '等待处理', running: '正在处理', succeeded: '处理完成', partial: '部分步骤未完成',
  failed: '处理失败', cancelled: '已取消', ok: '查询已完成', rate_limited: '来源暂时限流',
  error: '来源访问失败', disabled: '来源未启用', not_configured: '来源尚未配置',
  timeout: '来源响应超时', abstract_acquired: '已补充摘要', source_unavailable: '来源暂不可用',
};
export function gapState(value: string): string { return states[value] ?? '状态待核实'; }
export function planCategory(value: string): string {
  return ({ literature: '补充文献', data: '准备材料', dataset: '准备材料', baseline: '建立对照',
    experiment: '开展实验', evaluation: '核验结果', validation: '核验结果', review: '人工复核',
    reproduction: '复现实验', writing: '整理结论', risk: '风险核查', ablation: '核验组成贡献' } as Record<string, string>)[value] ?? '下一步行动';
}
// Only explicit display fields are accepted. Bibliographic names and original quotes stay verbatim.
export function evidenceText(value: unknown): string {
  if (typeof value === 'string') return value.trim() || missing;
  if (Array.isArray(value)) return value.length ? value.map(evidenceText).join('；') : missing;
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const labels: Record<string, string> = { input: '输入', output: '输出', setting: '研究条件',
      claim: '原文陈述', supporting_text: '原文依据', title: '论文' };
    return Object.entries(labels).filter(([key]) => typeof record[key] === 'string' && record[key])
      .map(([key, label]) => `${label}：${record[key]}`).join('；') || missing;
  }
  return missing;
}
export function directEvidenceText(value: Record<string, unknown>): string {
  const title = typeof value.title === 'string' ? value.title : '所选论文';
  const quote = typeof value.supporting_text === 'string' ? value.supporting_text : '请回到论文核查原文与定位信息';
  return `${title}：${quote}`;
}
export function evidenceEvent(value: string): string {
  return ({ created: '开始准备材料', started: '开始获取材料', identity_resolution: '核对论文身份',
    abstract_acquisition: '获取摘要', oa_resolution: '核对公开全文许可', fulltext_ingestion: '获取并解析正文',
    structured_analysis: '整理材料依据', llm_analysis: '核对分析结果', author_refresh: '更新作者信息',
    dataset_refresh: '更新数据集信息', succeeded: '处理完成', partial: '部分步骤未完成',
    failed: '处理失败', cancelled: '已取消' } as Record<string, string>)[value] ?? '材料处理进展';
}
