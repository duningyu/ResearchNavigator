import { Button, Card, Space, Tag, Typography } from 'antd';
import { useMemo, useState } from 'react';
import type { Citation, PaperAnalysisBody } from '../types/domain';

type Props = { analysis: PaperAnalysisBody };

const sections: Array<{ key: keyof NonNullable<PaperAnalysisBody['quick_interpretation_zh']>; label: string; evidenceField: string }> = [
  { key: 'overview', label: '研究概览', evidenceField: 'executive_summary' },
  { key: 'background', label: '研究背景', evidenceField: 'research_background' },
  { key: 'problem', label: '研究问题', evidenceField: 'research_problem' },
  { key: 'task', label: '任务定义', evidenceField: 'task_definition' },
  { key: 'method', label: '核心方法', evidenceField: 'core_methods' },
  { key: 'result', label: '主要结果', evidenceField: 'major_results' },
];

function materialLabel(level: string) {
  return level.includes('fulltext') ? '正文级 / 开放全文材料' : '摘要级初步分析';
}

function citationKey(citation: Citation) {
  return [citation.source_type, citation.section, citation.page_start, citation.page_end, citation.chunk_id, citation.supporting_text].join('|');
}

function sourceLabel(citation: Citation) {
  return citation.source_type === 'abstract' ? '来源：Abstract' : `来源：${citation.source_type || '原文证据'}`;
}

export function QuickInterpretationPanel({ analysis }: Props) {
  const [expanded, setExpanded] = useState(false);
  const quick = analysis.quick_interpretation_zh;
  const citations = useMemo(() => {
    const all = sections.flatMap(({ evidenceField }) => analysis.field_citations[evidenceField] ?? []);
    return Array.from(new Map(all.filter((item) => item.supporting_text).map((item) => [citationKey(item), item])).values());
  }, [analysis.field_citations]);

  return <Card title="快速解读">
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Space wrap>
        <Tag color="blue">当前材料：{materialLabel(analysis.evidence_level)}</Tag>
        <Tag>{quick ? '中文展示内容' : '原始证据可用'}</Tag>
      </Space>
      {quick ? sections.map(({ key, label }) => quick[key] ? <section key={key} aria-label={label}>
        <Typography.Title level={5}>{label}</Typography.Title>
        <Typography.Paragraph>{quick[key]}</Typography.Paragraph>
      </section> : null) : <>
        <Typography.Text>中文快速解读暂不可用</Typography.Text>
        <Typography.Paragraph type="secondary">查看原始证据</Typography.Paragraph>
      </>}
      {citations.length > 0 && <>
        <Button size="small" onClick={() => setExpanded((value) => !value)}>查看原文证据</Button>
        {expanded && <Space orientation="vertical" style={{ width: '100%' }}>
          {citations.map((citation) => <div key={citationKey(citation)}>
            <Tag>{sourceLabel(citation)}</Tag>
            <blockquote>{citation.supporting_text}</blockquote>
          </div>)}
        </Space>}
      </>}
    </Space>
  </Card>;
}
