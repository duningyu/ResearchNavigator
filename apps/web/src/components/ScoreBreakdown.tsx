import { Alert, Descriptions, Progress, Space, Tag, Typography } from 'antd';
import type { ScoreResult } from '../types/domain';
import { clampScore, coveragePercent } from './scoreMath';
import { scoreLabels } from '../lib/researchDisplay';

export function ScoreBreakdown({ title, score }: { title: string; score: ScoreResult }) {
  const coverage = coveragePercent(score.evidence_coverage);
  const reproduction = title === '复现准备情况';
  const dimensionStatus: Record<string, string> = { verified: '已核验', partial: '部分证据', unknown: '尚未核验', missing: '确认缺失' };
  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Typography.Title level={5} style={{ margin: 0 }}>{title}</Typography.Title>
      {score.score === null ? <Tag color="default">{reproduction ? '信息不足，暂不评分' : '暂无法判断'}</Tag> : <Progress percent={clampScore(score.score)} status="active" />}
      {reproduction && score.score !== null && <Typography.Text>当前准备度 {clampScore(score.score)}%</Typography.Text>}
      <Tag>证据覆盖 {coverage === null ? '尚未评估' : `${coverage}%`}</Tag>
      {!reproduction && score.score !== null && coverage !== null && coverage < 80 && (
        <Alert
          type="info"
          showIcon
          message="初步判断"
          description="当前结果基于研究课题、论文元数据/摘要和已获得证据；补充正文后结论可能变化。"
        />
      )}
      {reproduction && score.dimensions && <Descriptions size="small" bordered column={1}>
        {score.dimensions.map((dimension) => <Descriptions.Item key={dimension.name} label={scoreLabels[dimension.name] ?? dimension.name}>
          <Tag>{dimensionStatus[dimension.status] ?? '尚未核验'}</Tag> {dimension.evidence}
        </Descriptions.Item>)}
      </Descriptions>}
      {reproduction && score.recommended_first_step && <Alert type="info" showIcon message="建议下一步" description={score.recommended_first_step} />}
      {score.components && (
        <Descriptions size="small" bordered column={1}>
          {Object.entries(score.components).filter(([key]) => Object.hasOwn(scoreLabels, key)).map(([key, value]) => (
            <Descriptions.Item key={key} label={scoreLabels[key]}>
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
          description={score.blocking_reasons.map((key) => Object.hasOwn(scoreLabels, key) ? scoreLabels[key] : '其他条件尚需核验').join('、')}
        />
      )}
    </Space>
  );
}
