import {
  BookOutlined,
  CompassOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuOutlined,
  MenuUnfoldOutlined,
  SafetyCertificateOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Drawer, Grid, Layout, Menu, Space, Typography } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

const { Header, Sider, Content } = Layout;

const baseItems = [
  ['/', <DashboardOutlined />, '研究首页'],
  ['/search', <FileSearchOutlined />, '找论文'],
  ['/library', <BookOutlined />, '我的论文'],
  ['/compare', <UnorderedListOutlined />, '比较与找空白'],
  ['/plans', <UnorderedListOutlined />, '下一步计划'],
].map(([key, icon, label]) => ({ key: key as string, icon, label }));

const pageTitles: Record<string, string> = {
  '/': '研究工作台', '/profile': '研究档案', '/projects': '研究课题', '/search': '论文检索', '/library': '我的论文库', '/compare': '论文对比', '/gaps': '候选研究空白', '/plans': '研究计划', '/jobs': '任务进度', '/direction-map': '方向聚类', '/evaluations': '专家评测', '/sources': '数据源状态', '/settings': '设置', '/backup': '备份与恢复', '/admin': '管理员配置',
};
const APP_HISTORY_KEY = 'rn-app-navigation-v1';
const fallbackRoutes: Record<string, string> = { '/profile': '/', '/projects': '/', '/settings': '/', '/sources': '/', '/library': '/', '/papers': '/search', '/compare': '/', '/gaps': '/compare', '/plans': '/' };

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, clearSession } = useAuth();
  const screens = Grid.useBreakpoint();
  const desktop = Boolean(screens.lg);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const contentRef = useRef<HTMLElement>(null);
  const previousPath = useRef(`${location.pathname}${location.search}${location.hash}`);
  const pageTitle = pageTitles[location.pathname] ?? '研究工作台';
  const userInitial = (user?.display_name ?? user?.email ?? 'R').slice(0, 1).toUpperCase();
  const adminItems = user?.is_admin ? [
    { key: '/backup', icon: <DatabaseOutlined />, label: '备份与恢复' },
    { key: '/admin', icon: <SafetyCertificateOutlined />, label: '管理员配置' },
  ] : [];
  const items = [...baseItems, ...adminItems];
  const go = (key: string) => {
    const project = new URLSearchParams(location.search).get('project');
    const scopedDestination = baseItems.some((item) => item.key === key);
    // Carry only the explicit direction scope, never another screen's result/ticket parameters.
    navigate(scopedDestination && project && /^[1-9]\d*$/.test(project)
      ? `${key}?${new URLSearchParams({ project })}` : key);
    setDrawerOpen(false);
  };
  const locationKey = `${location.pathname}${location.search}${location.hash}`;
  const readHistory = () => { try { const parsed = JSON.parse(sessionStorage.getItem(APP_HISTORY_KEY) ?? '[]'); return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === 'string' && value.startsWith('/')) : []; } catch { return []; } };
  const safeBack = () => {
    const stack = readHistory();
    const previous = stack.pop();
    sessionStorage.setItem(APP_HISTORY_KEY, JSON.stringify(stack.slice(-30)));
    if (previous && previous !== locationKey) { navigate(previous); return; }
    const fallback = Object.entries(fallbackRoutes).find(([prefix]) => location.pathname === prefix || location.pathname.startsWith(`${prefix}/`))?.[1] ?? '/';
    const project = new URLSearchParams(location.search).get('project');
    navigate(project && fallback !== '/' ? `${fallback}?project=${encodeURIComponent(project)}` : fallback);
  };

  useEffect(() => {
    const from = previousPath.current;
    previousPath.current = locationKey;
    if (from === locationKey) return;
    const stack = readHistory();
    if (from.startsWith('/') && from !== locationKey && stack[stack.length - 1] !== from) sessionStorage.setItem(APP_HISTORY_KEY, JSON.stringify([...stack, from].slice(-30)));
    const returningToSearch = from.startsWith('/papers/') && location.pathname === '/search';
    const frame = requestAnimationFrame(() => {
      if (returningToSearch) {
        const restoredTarget = document.querySelector<HTMLElement>('[data-search-paper]');
        if (restoredTarget) {
          restoredTarget.focus({ preventScroll: true });
          return;
        }
      }
      contentRef.current?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [locationKey]);

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
          <div><Typography.Text className="header-overline">研途智选</Typography.Text><Typography.Title level={4}>{pageTitle}</Typography.Title></div>
        </Space>
        <Space size="middle">
          <div className="header-user"><Avatar>{userInitial}</Avatar><span><strong>{user?.display_name ?? user?.email}</strong><small>研究空间</small></span></div>
          {location.pathname !== '/' && <Button onClick={safeBack}>← 返回</Button>}
          <Button onClick={() => go('/settings')}>设置与来源</Button>
          <Button className="logout-button" icon={<LogoutOutlined />} onClick={() => void clearSession()}>退出</Button>
        </Space>
      </Header>
      <Content ref={contentRef} className="app-content" tabIndex={-1}><Outlet /></Content>
    </Layout>
  </Layout>;
}
