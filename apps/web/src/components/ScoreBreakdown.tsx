import { Alert, Descriptions, Progress, Space, Tag, Typography } from 'antd';
import type { ScoreResult } from '../types/domain';
import { clampScore, coveragePercent } from './scoreMath';

export function ScoreBreakdown({ title, score }: { title: string; score: ScoreResult }) {
  const coverage = coveragePercent(score.evidence_coverage);
  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Typography.Title level={5} style={{ margin: 0 }}>{title}</Typography.Title>
      <Progress percent={clampScore(score.score)} status="active" />
      <Tag>证据覆盖 {coverage}%</Tag>
      {score.components && (
        <Descriptions size="small" bordered column={1}>
          {Object.entries(score.components).map(([key, value]) => (
            <Descriptions.Item key={key} label={key}>
              {value === null ? '缺失，不参与归一化' : `${Math.round(value * 100)}%`}
            </Descriptions.Item>
          ))}
        </Descriptions>
      )}
      {!!score.blocking_reasons?.length && (
        <Alert
          type="warning"
          showIcon
          message="复现阻断项"
          description={score.blocking_reasons.join('、')}
        />
      )}
    </Space>
  );
}
