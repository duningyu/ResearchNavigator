import { Alert, Button, Card, Checkbox, Col, Descriptions, InputNumber, List, Row, Select, Space, Statistic, Tag, Typography, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../api/client';
import type { DirectionClusterRun, LibraryItem, Project } from '../types/domain';

type LibraryPayload = { items: LibraryItem[] };

const DIRECTION_DISCLAIMER = '这是一种文献组织结果，不是学术领域的客观分类。 This is a literature-organization result, not an objective field taxonomy.';

export function DirectionMapPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [library, setLibrary] = useState<LibraryPayload>({ items: [] });
  const [projectId, setProjectId] = useState<number | null>(null);
  const [paperIds, setPaperIds] = useState<number[]>([]);
  const [threshold, setThreshold] = useState(0.2);
  const [run, setRun] = useState<DirectionClusterRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void apiRequest<Project[]>('/projects').then(setProjects).catch(() => setProjects([]));
    void apiRequest<LibraryPayload>('/library').then(setLibrary).catch(() => setLibrary({ items: [] }));
  }, []);

  const favorites = useMemo(() => library.items.filter((item) => item.favorite), [library]);
  const titleById = useMemo(() => new Map(favorites.map((item) => [item.paper.id, item.paper.title])), [favorites]);
  const membersByCluster = useMemo(() => {
    const grouped = new Map<string, typeof run.members>();
    if (!run) return grouped;
    for (const member of run.members) {
      const key = member.cluster_key ?? 'unclustered';
      grouped.set(key, [...(grouped.get(key) ?? []), member]);
    }
    return grouped;
  }, [run]);

  const execute = async () => {
    if (!projectId) { message.error('请先选择研究项目'); return; }
    if (paperIds.length < 2) { message.error('方向聚类至少需要两篇论文'); return; }
    setBusy(true); setError(null);
    try {
      const value = await apiRequest<DirectionClusterRun>(`/projects/${projectId}/direction-clusters`, {
        method: 'POST',
        body: JSON.stringify({ paper_ids: paperIds, threshold }),
      });
      setRun(value);
      message.success('方向聚类已完成；结果已绑定算法版本、参数和输入哈希');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  return <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <Alert
      type="warning"
      showIcon
      title="方向聚类用于组织文献，不是学科领域的客观分类"
      description="当前 direction-cluster-v1 使用确定性文本向量、相似度图和连通分量。它不证明研究方向成立，也不替代专家分类（not an objective field taxonomy）。"
    />
    {error && <Alert type="error" showIcon title="方向聚类失败" description={error} />}
    <Card title="选择项目与论文">
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Select
          aria-label="研究项目"
          placeholder="选择研究项目"
          value={projectId ?? undefined}
          options={projects.map((project) => ({ value: project.id, label: `${project.name}${project.broad_direction ? ` · ${project.broad_direction}` : ''}` }))}
          onChange={setProjectId}
          style={{ width: '100%', maxWidth: 560 }}
        />
        <Space wrap>
          <Typography.Text>相似度阈值</Typography.Text>
          <InputNumber min={0} max={1} step={0.05} value={threshold} onChange={(value) => setThreshold(value ?? 0.2)} />
          <Typography.Text type="secondary">阈值越高，聚类越保守；参数变化会生成新的可审计运行。</Typography.Text>
        </Space>
        <Checkbox.Group value={paperIds} onChange={(values) => setPaperIds(values as number[])} style={{ width: '100%' }}>
          <List
            bordered
            dataSource={favorites}
            locale={{ emptyText: '论文库中没有收藏论文；请先收藏论文。' }}
            renderItem={(item) => <List.Item>
              <Checkbox value={item.paper.id}>
                <Space wrap><Link to={`/papers/${item.paper.id}`}>{item.paper.title}</Link><Tag>{item.paper.publication_year ?? '年份未知'}</Tag><Tag>{item.paper.abstract_evidence_verified ? '可信摘要' : '证据待补'}</Tag></Space>
              </Checkbox>
            </List.Item>}
          />
        </Checkbox.Group>
        <Button type="primary" loading={busy} disabled={!projectId || paperIds.length < 2} onClick={() => void execute()}>生成方向聚类</Button>
      </Space>
    </Card>

    {run && <>
      <Alert type="info" showIcon title={run.disclaimer} description={`algorithm=${run.algorithm_version} · input_hash=${run.input_hash}`} />
      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}><Card><Statistic title="聚类数量" value={run.clusters.length} /></Card></Col>
        <Col xs={24} md={8}><Card><Statistic title="论文数量" value={run.members.length} /></Card></Col>
        <Col xs={24} md={8}><Card><Statistic title="未归类论文" value={run.members.filter((member) => member.is_unclustered).length} /></Card></Col>
      </Row>
      <Card title="方向聚类结果">
        <List
          dataSource={[...run.clusters, { id: -1, cluster_key: 'unclustered', label: '未归类论文', terms: [], evidence_distribution: {} }]}
          renderItem={(cluster) => {
            const members = membersByCluster.get(cluster.cluster_key) ?? [];
            if (!members.length) return null;
            return <List.Item>
              <List.Item.Meta
                title={<Space wrap><Typography.Text strong>{cluster.label}</Typography.Text><Tag>{cluster.cluster_key}</Tag>{cluster.terms.map((term) => <Tag key={term} color="blue">{term}</Tag>)}</Space>}
                description={<Space orientation="vertical" style={{ width: '100%' }}>
                  <Descriptions size="small" column={1}>
                    <Descriptions.Item label="证据等级分布">{Object.entries(cluster.evidence_distribution).map(([level, count]) => <Tag key={level}>{level}: {count}</Tag>)}</Descriptions.Item>
                  </Descriptions>
                  {members.map((member) => <Space key={member.paper_id} wrap><Link to={`/papers/${member.paper_id}`}>{titleById.get(member.paper_id) ?? `Paper #${member.paper_id}`}</Link><Tag>{member.is_unclustered ? 'unclustered' : `similarity=${member.similarity.toFixed(3)}`}</Tag></Space>)}
                </Space>}
              />
            </List.Item>;
          }}
        />
      </Card>
    </>}
  </Space>;
}
