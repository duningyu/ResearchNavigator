import { ArrowRightOutlined, BookOutlined, FileSearchOutlined, FolderAddOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Col, Row, Space, Statistic, Tag, Typography } from 'antd';
import { Link } from 'react-router-dom';

export function DashboardPage() {
  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <section className="dashboard-hero">
        <div><Tag className="section-tag">用证据推进研究</Tag><Typography.Title level={1}>今日研究起点</Typography.Title><Typography.Paragraph>先建立方向与约束，再检索、阅读、反证和形成可执行计划。每一步都应保留可追溯依据。</Typography.Paragraph></div>
        <div className="dashboard-actions"><Link to="/search"><Button type="primary" size="large" icon={<FileSearchOutlined />}>开始检索</Button></Link><Link to="/projects"><Button size="large" icon={<FolderAddOutlined />}>新建项目</Button></Link></div>
      </section>
      <Alert className="boundary-alert" type="warning" showIcon title="科研主张边界" description="候选研究空白不是创新性证明。请保留检索式、数据源、反向证据和人工确认记录。" />
      <Row gutter={[20, 20]}>
        <Col xs={24} md={8}><Card className="metric-card"><Statistic title="核心工作流" value="研究证据" prefix={<SafetyCertificateOutlined />} /><Typography.Text type="secondary">从来源到人工确认保持可追溯。</Typography.Text></Card></Col>
        <Col xs={24} md={8}><Card className="metric-card"><Statistic title="我的研究资料" value="按账号保存" prefix={<BookOutlined />} /><Typography.Text type="secondary">论文、集合与笔记可在我的论文中继续查看。</Typography.Text></Card></Col>
        <Col xs={24} md={8}><Card className="metric-card"><Statistic title="数据与来源" value="以当前连接的服务为准" prefix={<FolderAddOutlined />} /><Typography.Text type="secondary">来源状态请在设置中核对；页面不预设本地或云端部署。</Typography.Text></Card></Col>
      </Row>
      <Card className="workflow-card" title="推荐研究路径" extra={<Link to="/profile">完善档案 <ArrowRightOutlined /></Link>}>
        <Row gutter={[16, 16]}>
          {[['01', '建立研究档案', '明确阶段、方向、算力与排除条件', '/profile'], ['02', '检索与入库', '用真实来源建立论文证据集合', '/search'], ['03', '阅读与反证', '分析全文证据，挑战候选空白', '/gaps'], ['04', '形成最小计划', '人工确认后生成可执行研究计划', '/plans']].map(([index, title, description, to]) => <Col xs={24} sm={12} xl={6} key={index}><Link className="workflow-step" to={to}><span>{index}</span><strong>{title}</strong><small>{description}</small><ArrowRightOutlined /></Link></Col>)}
        </Row>
      </Card>
    </Space>
  );
}
