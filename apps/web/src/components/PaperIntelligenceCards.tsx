import { Card, Col, Descriptions, Empty, List, Row, Space, Tag, Typography } from 'antd';
import type { AuthorCard, DatasetCard } from '../types/domain';
import { gapState } from '../lib/researchDisplay';

type Props = { authors: AuthorCard[]; datasets: DatasetCard[]; loading: boolean };
const absent = '未在当前可访问证据中找到。';
const text = (value: unknown) => value === null || value === undefined || value === '' ? absent : String(value);
const listText = (values: string[]) => values.length ? values.join('；') : absent;
const identityText = (value: string) => ({ resolved: '已核对来源标识',
  resolved_identifier: '已核对来源标识', mentioned_only: '仅在原文中提及',
  unresolved: '身份待核实' } as Record<string, string>)[value] ?? '身份待核实';
const roleText = (value: string | null | undefined) => ({ evaluation: '用于评价', training: '用于训练',
  validation: '用于验证', benchmark: '用于基准比较' } as Record<string, string>)[value ?? ''] ?? '用途待核实';
const provenanceSources = (items: Array<Record<string, unknown>>) => {
  const names = items.map((item) => item.source).filter((item): item is string => typeof item === 'string');
  return names.length ? [...new Set(names)].join('、') : absent;
};

export function PaperIntelligenceCards({ authors, datasets, loading }: Props) {
  return <Row gutter={[16, 16]}>
    <Col xs={24} xl={12}><Card title="作者卡（来源可验证，不按姓名强制合并）" loading={loading}>
      {authors.length === 0 ? <Empty description="尚无可验证作者卡；不会根据姓名猜测作者身份或贡献。" /> : <List dataSource={authors} renderItem={(author) => <List.Item>
        <Card size="small" style={{ width: '100%' }} title={<Space wrap><Typography.Text strong>{author.canonical_name}</Typography.Text><Tag>{identityText(author.identity_status)}</Tag>{author.position ? <Tag>第 {author.position} 位作者</Tag> : null}</Space>}>
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="ORCID">{text(author.orcid)}</Descriptions.Item>
            <Descriptions.Item label="机构">{listText(author.affiliations)}</Descriptions.Item>
            <Descriptions.Item label="研究主题">{listText(author.topics)}</Descriptions.Item>
            <Descriptions.Item label="论文数 / 引用数">{author.works_count ?? absent} / {author.citation_count ?? absent}</Descriptions.Item>
            <Descriptions.Item label="CRediT 角色">{listText(author.credit_roles)}</Descriptions.Item>
            <Descriptions.Item label="数据来源">{provenanceSources(author.provenance)}</Descriptions.Item>
          </Descriptions>
        </Card>
      </List.Item>} />}
    </Card></Col>
    <Col xs={24} xl={12}><Card title="数据集卡（仅展示当前文本支持的字段）" loading={loading}>
      {datasets.length === 0 ? <Empty description="尚未从当前论文证据中识别出数据集；不会自行补造样本规模、切分或许可证。" /> : <List dataSource={datasets} renderItem={(dataset) => <List.Item>
        <Card size="small" style={{ width: '100%' }} title={<Space wrap><Typography.Text strong>{dataset.canonical_name}</Typography.Text><Tag>{identityText(dataset.identity_status)}</Tag>{dataset.evidence_level && <Tag color="blue">{gapState(dataset.evidence_level)}</Tag>}</Space>}>
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="原文提及">{text(dataset.raw_mention)}</Descriptions.Item>
            <Descriptions.Item label="角色 / 任务">{roleText(dataset.role)} / {text(dataset.task)}</Descriptions.Item>
            <Descriptions.Item label="领域">{text(dataset.domain)}</Descriptions.Item>
            <Descriptions.Item label="许可证">{text(dataset.license)}</Descriptions.Item>
            <Descriptions.Item label="训练 / 验证 / 测试划分">{text(dataset.train_split)} / {text(dataset.validation_split)} / {text(dataset.test_split)}</Descriptions.Item>
            <Descriptions.Item label="指标">{listText(dataset.metrics)}</Descriptions.Item>
            <Descriptions.Item label="数据来源">{provenanceSources(dataset.provenance)}</Descriptions.Item>
          </Descriptions>
        </Card>
      </List.Item>} />}
    </Card></Col>
  </Row>;
}
