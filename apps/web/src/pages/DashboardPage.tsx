import { ArrowRightOutlined, BookOutlined, FileSearchOutlined, FolderAddOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Col, Row, Space, Statistic, Tag, Typography } from 'antd';
import { Link } from 'react-router-dom';

export function DashboardPage() {
  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <section className="dashboard-hero">
        <div><Tag className="section-tag">EVIDENCE-FIRST WORKFLOW</Tag><Typography.Title level={1}>今日研究起点</Typography.Title><Typography.Paragraph>先建立方向与约束，再检索、阅读、反证和形成可执行计划。每一步都应保留可追溯依据。</Typography.Paragraph></div>
        <div className="dashboard-actions"><Link to="/search"><Button type="primary" size="large" icon={<FileSearchOutlined />}>开始检索</Button></Link><Link to="/projects"><Button size="large" icon={<FolderAddOutlined />}>新建项目</Button></Link></div>
      </section>
      <Alert className="boundary-alert" type="warning" showIcon title="科研主张边界" description="候选研究空白不是创新性证明。请保留检索式、数据源、反向证据和人工确认记录。" />
      <Row gutter={[20, 20]}>
        <Col xs={24} md={8}><Card className="metric-card"><Statistic title="核心工作流" value="研究证据" prefix={<SafetyCertificateOutlined />} /><Typography.Text type="secondary">从来源到人工确认保持可追溯。</Typography.Text></Card></Col>
        <Col xs={24} md={8}><Card className="metric-card"><Statistic title="本地持久化" value="SQLite" prefix={<BookOutlined />} /><Typography.Text type="secondary">项目、论文库与笔记保存在本地运行目录。</Typography.Text></Card></Col>
        <Col xs={24} md={8}><Card className="metric-card"><Statistic title="当前部署" value="本地运行" prefix={<FolderAddOutlined />} /><Typography.Text type="secondary">服务状态可在数据源和任务页进一步核对。</Typography.Text></Card></Col>
      </Row>
      <Card className="workflow-card" title="推荐研究路径" extra={<Link to="/profile">完善档案 <ArrowRightOutlined /></Link>}>
        <Row gutter={[16, 16]}>
          {[['01', '建立研究档案', '明确阶段、方向、算力与排除条件', '/profile'], ['02', '检索与入库', '用真实来源建立论文证据集合', '/search'], ['03', '阅读与反证', '分析全文证据，挑战候选空白', '/gaps'], ['04', '形成最小计划', '人工确认后生成可执行研究计划', '/plans']].map(([index, title, description, to]) => <Col xs={24} sm={12} xl={6} key={index}><Link className="workflow-step" to={to}><span>{index}</span><strong>{title}</strong><small>{description}</small><ArrowRightOutlined /></Link></Col>)}
        </Row>
      </Card>
    </Space>
  );
}
