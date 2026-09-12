import { Button, Card, Checkbox, Input, List, Progress, Select, Space, Tag, Typography, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiRequest } from '../api/client';
import type { LibraryItem, PaperSet } from '../types/domain';

type LibraryPayload = { items: LibraryItem[] };
const readingStatusLabels: Record<string, string> = { unread: '未读', queued: '待读', reading: '阅读中', read: '已读', reproducing: '复现中', archived: '已归档' };

export function LibraryPage() {
  const navigate = useNavigate();
  const [library, setLibrary] = useState<LibraryPayload>({ items: [] });
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [noteDrafts, setNoteDrafts] = useState<Record<number, string>>({});
  const [tagDrafts, setTagDrafts] = useState<Record<number, string>>({});
  const load = () => void apiRequest<LibraryPayload>('/library').then(setLibrary);
  useEffect(load, []);
  const favorites = useMemo(() => library.items.filter((item) => item.favorite), [library]);

  const createSetAndNavigate = async (purpose: 'compare' | 'gap') => {
    if (selectedIds.length < (purpose === 'compare' ? 2 : 1)) { message.error(purpose === 'compare' ? '论文对比至少选择两篇论文' : '候选研究空白至少选择一篇论文'); return; }
    const paperSet = await apiRequest<PaperSet>('/paper-sets', { method: 'POST', body: JSON.stringify({ project_id: null, purpose, name: `${purpose === 'compare' ? '收藏论文对比' : '收藏论文空白探索'} · ${new Date().toLocaleString()}`, paper_ids: selectedIds, source_kind: 'favorites' }) });
    navigate(`/${purpose === 'compare' ? 'compare' : 'gaps'}?paperSet=${paperSet.id}`);
  };
  const addNote = async (paperId: number) => { const content = (noteDrafts[paperId] ?? '').trim(); if (!content) return; await apiRequest('/library/notes', { method: 'POST', body: JSON.stringify({ paper_id: paperId, content }) }); setNoteDrafts((current) => ({ ...current, [paperId]: '' })); load(); };
  const addTag = async (paperId: number) => { const name = (tagDrafts[paperId] ?? '').trim(); if (!name) return; const tag = await apiRequest<{ id: number; name: string }>('/library/tags', { method: 'POST', body: JSON.stringify({ name }) }); await apiRequest(`/library/papers/${paperId}/tags/${tag.id}`, { method: 'POST' }); setTagDrafts((current) => ({ ...current, [paperId]: '' })); load(); };
  const setReading = async (paperId: number, status: string, progress: number) => { await apiRequest(`/library/papers/${paperId}/reading-status`, { method: 'PUT', body: JSON.stringify({ status, progress }) }); load(); };
  const removeFavorite = async (paperId: number) => { await apiRequest(`/library/favorites/${paperId}`, { method: 'DELETE' }); setSelectedIds((ids) => ids.filter((id) => id !== paperId)); load(); };

  return <Space orientation="vertical" size="large" style={{ width: '100%' }}>
    <Card title="我的论文库" extra={<Space><Button disabled={selectedIds.length < 2} onClick={() => void createSetAndNavigate('compare')}>对比选中论文</Button><Button type="primary" disabled={!selectedIds.length} onClick={() => void createSetAndNavigate('gap')}>探索候选研究空白</Button></Space>}>
      <Typography.Paragraph type="secondary">收藏不只是书签。勾选论文后会生成显式 paper set，可在论文对比和候选研究空白中与自己选择的研究项目/方向共同使用。</Typography.Paragraph>
      <Checkbox.Group value={selectedIds} onChange={(ids) => setSelectedIds(ids as number[])} style={{ width: '100%' }}>
        <List dataSource={favorites} locale={{ emptyText: '尚未收藏论文' }} renderItem={(row) => <List.Item className="library-paper-row">
          <div className="library-paper-select"><Checkbox value={row.paper.id} /></div>
          <List.Item.Meta className="library-paper-main" title={<Space wrap><Link to={`/papers/${row.paper.id}`}>{row.paper.title}</Link><Tag>{row.paper.publication_year ?? '年份未知'}</Tag>{row.tags.map((tag) => <Tag key={tag.id} color="blue">{tag.name}</Tag>)}</Space>} description={<Space orientation="vertical" style={{ width: '100%' }}>
            <Space wrap><Select aria-label="阅读状态" size="small" value={row.reading_status?.status ?? 'unread'} style={{ width: 130 }} options={Object.entries(readingStatusLabels).map(([value, label]) => ({ value, label }))} onChange={(status) => void setReading(row.paper.id, status, row.reading_status?.progress ?? 0)} /><Progress size="small" style={{ width: 160 }} percent={row.reading_status?.progress ?? 0} /><Button size="small" danger onClick={() => void removeFavorite(row.paper.id)}>取消收藏</Button></Space>
            {row.notes.map((note) => <Typography.Text key={note.id} type="secondary">笔记：{note.content}</Typography.Text>)}
            <Space.Compact style={{ maxWidth: 560, width: '100%' }}><Input size="small" placeholder="新增研究笔记" value={noteDrafts[row.paper.id] ?? ''} onChange={(event) => setNoteDrafts((current) => ({ ...current, [row.paper.id]: event.target.value }))} /><Button size="small" onClick={() => void addNote(row.paper.id)}>保存</Button></Space.Compact>
            <Space.Compact style={{ maxWidth: 420, width: '100%' }}><Input size="small" placeholder="新增标签" value={tagDrafts[row.paper.id] ?? ''} onChange={(event) => setTagDrafts((current) => ({ ...current, [row.paper.id]: event.target.value }))} /><Button size="small" onClick={() => void addTag(row.paper.id)}>添加</Button></Space.Compact>
          </Space>} />
        </List.Item>} />
      </Checkbox.Group>
    </Card>
  </Space>;
}
