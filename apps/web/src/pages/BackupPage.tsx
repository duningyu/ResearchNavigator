import { Alert, Button, Card, List, Popconfirm, Space, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { apiDownload, apiRequest } from '../api/client';

type Backup = { name: string; size_bytes: number; sha256: string; created_at: string };
type Staged = { backup_name: string; backup_sha256: string; staged_at: string; restart_required: boolean };

export function BackupPage() {
  const [backups, setBackups] = useState<Backup[]>([]);
  const [staged, setStaged] = useState<Staged | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => void apiRequest<Backup[]>('/admin/backups').then(setBackups).catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  useEffect(load, []);
  const create = async () => { setBusy(true); setError(null); try { const backup = await apiRequest<Backup>('/admin/backups', { method: 'POST' }); message.success(`备份已创建：${backup.name}`); load(); } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); } finally { setBusy(false); } };
  const stageRestore = async (backup: Backup) => { setBusy(true); setError(null); try { const result = await apiRequest<Staged>(`/admin/backups/${encodeURIComponent(backup.name)}/stage-restore`, { method: 'POST', body: JSON.stringify({ confirm_restore: true }) }); setStaged(result); message.warning('恢复已安全暂存；重启服务后才会在打开 SQLite 前应用。'); } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); } finally { setBusy(false); } };
  return <Space orientation="vertical" size="large" style={{ width: '100%' }}><Alert type="warning" showIcon title="恢复不是在线覆盖 SQLite" description="为避免当前请求持有数据库连接时破坏文件，恢复采用 staged restore：先校验 ZIP/路径/SQLite integrity，再写 pending_restore；下次服务启动会在数据库引擎打开前原子替换数据库并恢复上传/向量目录。" />{staged && <Alert type="success" showIcon title={`已暂存恢复：${staged.backup_name}`} description="restart_required=true。重启前当前运行实例不会被修改。" />}{error && <Alert type="error" showIcon title="备份/恢复失败" description={error} />}<Card title="备份与恢复" extra={<Button type="primary" loading={busy} onClick={() => void create()}>创建一致性备份</Button>}><List dataSource={backups} locale={{ emptyText: '暂无备份' }} renderItem={(backup) => <List.Item actions={[<Button key="download" onClick={() => void apiDownload(`/admin/backups/${encodeURIComponent(backup.name)}/download`, backup.name)}>下载</Button>, <Popconfirm key="restore" title="暂存此备份用于下次启动恢复？" description="会恢复数据库、上传文件和向量状态；当前进程不会立即覆盖数据库。" okText="确认暂存" cancelText="取消" onConfirm={() => void stageRestore(backup)}><Button danger>暂存恢复</Button></Popconfirm>]}><List.Item.Meta title={<Space><Typography.Text strong>{backup.name}</Typography.Text><Tag>{(backup.size_bytes / 1024 / 1024).toFixed(2)} MB</Tag></Space>} description={`created=${backup.created_at} · sha256=${backup.sha256}`} /></List.Item>} /></Card></Space>;
}
