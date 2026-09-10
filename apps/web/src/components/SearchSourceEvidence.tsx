import { Space, Tag, Typography } from 'antd';
import type { SourceStatus } from '../types/domain';

const names: Record<string, string> = { fixture: '本地示例（非真实检索）', arxiv: 'arXiv', openalex: 'OpenAlex', crossref: 'Crossref', semantic_scholar: 'Semantic Scholar' };
const states: Record<string, string> = { ok: '已响应', error: '来源请求失败', disabled: '未启用', not_configured: '未配置', rate_limited: '来源限流' };

export function SearchSourceEvidence({ name, status }: { name: string; status: SourceStatus }) {
  const time = status.checked_at && Number.isFinite(Date.parse(status.checked_at))
    ? status.checked_at : null;
  const query = status.metadata?.executed_query;
  const adaptationStatus = status.metadata?.query_adaptation_status;
  const adaptationMode = status.metadata?.query_adaptation;
  const adaptationMessage = adaptationStatus === 'ADAPTED'
    && (adaptationMode === undefined || adaptationMode === 'controlled_glossary')
    ? '已补充英文检索词'
    : adaptationStatus === 'FALLBACK_ORIGINAL'
      ? '英文检索词暂未生成，已使用原关键词继续搜索'
      : null;
  return <Space direction="vertical" size={2}>
    <Tag color={status.status === 'ok' ? 'green' : 'default'}>
      {names[name] ?? '其他来源'}：{states[status.status] ?? '状态待确认'}
      {status.status === 'ok' && status.result_count === 0 ? '，未找到匹配结果' : ''}
    </Tag>
    <Typography.Text type="secondary">{time ? `本次检查：${time}` : '未提供本次检查时间'}</Typography.Text>
    {typeof query === 'string' && <Typography.Text>实际检索词：{query}</Typography.Text>}
    {adaptationMessage && <Typography.Text>{adaptationMessage}</Typography.Text>}
    <Typography.Text type="secondary">检索状态不代表全文可获取；全文情况请查看论文材料。</Typography.Text>
  </Space>;
}
