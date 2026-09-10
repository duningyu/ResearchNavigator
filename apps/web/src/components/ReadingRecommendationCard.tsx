import { Alert, Card, Descriptions, Tag, Typography } from 'antd';

import type { ReadingRecommendation } from '../types/domain';

const verdictLabels: Record<ReadingRecommendation['verdict'], string> = {
  priority_read: '优先阅读',
  method_reference: '方法参考',
  not_priority: '暂不优先',
  insufficient_evidence: '信息不足',
};

const evidenceLabels: Record<ReadingRecommendation['evidence_level'], string> = {
  metadata: '仅元数据',
  abstract: '摘要级依据',
  full_text: '正文级依据',
};

export function ReadingRecommendationCard({
  recommendation,
}: {
  recommendation: ReadingRecommendation | null;
}) {
  if (!recommendation) return null;
  return (
    <Card title="阅读建议" size="small" style={{ marginTop: 16 }}>
      <Descriptions column={1} size="small">
        <Descriptions.Item label="结论">
          <Tag color={recommendation.verdict === 'priority_read' ? 'green' : 'blue'}>
            {verdictLabels[recommendation.verdict]}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="为什么">{recommendation.rationale}</Descriptions.Item>
        <Descriptions.Item label="当前依据">{evidenceLabels[recommendation.evidence_level]}</Descriptions.Item>
        <Descriptions.Item label="适用范围">{recommendation.applicability}</Descriptions.Item>
        <Descriptions.Item label="仍需核实">
          {recommendation.missing_information.length ? (
            <ul style={{ margin: 0, paddingInlineStart: 20 }}>
              {recommendation.missing_information.map((item) => <li key={item}>{item}</li>)}
            </ul>
          ) : <Typography.Text>暂无</Typography.Text>}
        </Descriptions.Item>
      </Descriptions>
      {!recommendation.is_current && (
        <Alert
          type="warning"
          showIcon
          message="当前阅读建议需要根据新的研究方向重新生成。"
          style={{ marginTop: 12 }}
        />
      )}
    </Card>
  );
}
