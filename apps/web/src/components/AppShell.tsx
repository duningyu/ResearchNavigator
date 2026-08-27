import {
  BookOutlined,
  CompassOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  FolderOpenOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuOutlined,
  MenuUnfoldOutlined,
  ProfileOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Drawer, Grid, Layout, Menu, Space, Typography } from 'antd';
import { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

const { Header, Sider, Content } = Layout;

const baseItems = [
  ['/', <DashboardOutlined />, '概览'],
  ['/profile', <ProfileOutlined />, '研究档案'],
  ['/projects', <FolderOpenOutlined />, '研究项目'],
  ['/search', <FileSearchOutlined />, '论文搜索'],
  ['/library', <BookOutlined />, '我的论文库'],
  ['/compare', <UnorderedListOutlined />, '论文对比'],
  ['/gaps', <ExperimentOutlined />, '候选研究空白'],
  ['/plans', <UnorderedListOutlined />, '研究计划'],
  ['/jobs', <DatabaseOutlined />, '任务进度'],
  ['/direction-map', <ExperimentOutlined />, '方向聚类'],
  ['/evaluations', <SafetyCertificateOutlined />, '专家评测'],
  ['/sources', <DatabaseOutlined />, '数据源状态'],
  ['/settings', <SettingOutlined />, '设置'],
].map(([key, icon, label]) => ({ key: key as string, icon, label }));

const pageTitles: Record<string, string> = {
  '/': '研究工作台', '/profile': '研究档案', '/projects': '研究项目', '/search': '论文检索', '/library': '我的论文库', '/compare': '论文对比', '/gaps': '候选研究空白', '/plans': '研究计划', '/jobs': '任务进度', '/direction-map': '方向聚类', '/evaluations': '专家评测', '/sources': '数据源状态', '/settings': '设置', '/backup': '备份与恢复', '/admin': '管理员配置',
};

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, clearSession } = useAuth();
  const screens = Grid.useBreakpoint();
  const desktop = Boolean(screens.lg);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const pageTitle = pageTitles[location.pathname] ?? '研究工作台';
  const userInitial = (user?.display_name ?? user?.email ?? 'R').slice(0, 1).toUpperCase();
  const adminItems = user?.is_admin ? [
    { key: '/backup', icon: <DatabaseOutlined />, label: '备份与恢复' },
    { key: '/admin', icon: <SafetyCertificateOutlined />, label: '管理员配置' },
  ] : [];
  const items = [...baseItems, ...adminItems];
  const go = (key: string) => { navigate(key); setDrawerOpen(false); };

  const navigation = <>
    <div className="brand"><span className="brand-mark">R</span>{!collapsed && <span><strong>研途智选</strong><small>RESEARCH NAVIGATOR</small></span>}</div>
    {!collapsed && <div className="sider-context"><CompassOutlined /><span>证据驱动的<br />研究工作空间</span></div>}
    {!collapsed && <Typography.Text className="nav-label">研究工作流</Typography.Text>}
    <Menu className="workspace-menu" mode="inline" inlineCollapsed={desktop && collapsed} items={items} selectedKeys={[location.pathname]} onClick={({ key }) => go(key)} />
    {!collapsed && <div className="sider-note"><span className="sider-note-dot" />候选空白必须经过反证与真实人工确认</div>}
  </>;

  return <Layout className="workspace-shell">
    {desktop && <Sider width={264} collapsedWidth={80} collapsed={collapsed} trigger={null} className="workspace-sider">{navigation}</Sider>}
    {!desktop && <Drawer title="ResearchNavigator" placement="left" size={290} open={drawerOpen} onClose={() => setDrawerOpen(false)} className="workspace-drawer"><div className="drawer-navigation">{navigation}</div></Drawer>}
    <Layout className="workspace-main" style={{ marginLeft: desktop ? (collapsed ? 80 : 264) : 0 }}>
      <Header className="app-header">
        <Space align="center">
          {desktop ? <Button className="nav-collapse-trigger" aria-label={collapsed ? '展开导航栏' : '收起导航栏'} icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} onClick={() => setCollapsed((value) => !value)} /> : <Button className="mobile-nav-trigger" aria-label="打开导航菜单" icon={<MenuOutlined />} onClick={() => setDrawerOpen(true)} />}
          <div><Typography.Text className="header-overline">RESEARCH SPACE</Typography.Text><Typography.Title level={4}>{pageTitle}</Typography.Title></div>
        </Space>
        <Space size="middle">
          <div className="header-user"><Avatar>{userInitial}</Avatar><span><strong>{user?.display_name ?? user?.email}</strong><small>本地研究空间</small></span></div>
          <Button className="logout-button" icon={<LogoutOutlined />} onClick={() => void clearSession()}>退出</Button>
        </Space>
      </Header>
      <Content className="app-content"><Outlet /></Content>
    </Layout>
  </Layout>;
}
