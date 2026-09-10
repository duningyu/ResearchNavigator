/** Metadata only: never store authentication, paper bodies or signed URLs. */
export type SearchWorkspace = {
  query: string;
  filters: { sources?: string[]; limit?: number; open_access_only?: boolean; mode?: string; adapt_query?: boolean; source_queries?: Record<string, string> };
  sessionId: number;
  resultIds: number[];
  selectedIds: number[];
  page: number;
  scrollY: number;
  anchor?: { paperId: number; offset: number };
};
export type SearchScope = { account: number; environment: string; project: number | null; tab: string };
type StoragePort = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
type Entry = { key: string; queryIdentity: string; savedAt: number; state: SearchWorkspace };
const KEY = 'rn-search-workspace-v4';
const TTL = 24 * 60 * 60 * 1000;
const identity = (scope: SearchScope) => JSON.stringify([scope.account, scope.environment, scope.project, scope.tab]);
const positiveInteger = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
const ids = (value: unknown): value is number[] => Array.isArray(value) && value.length <= 1000 && value.every(positiveInteger) && new Set(value).size === value.length;
function validState(value: unknown): value is SearchWorkspace {
  if (!value || typeof value !== 'object') return false;
  const state = value as SearchWorkspace;
  const filters = state.filters;
  return typeof state.query === 'string' && state.query.length <= 10000
    && positiveInteger(state.sessionId) && ids(state.resultIds) && ids(state.selectedIds)
    && state.selectedIds.every((id) => state.resultIds.includes(id))
    && positiveInteger(state.page) && Number.isFinite(state.scrollY) && state.scrollY >= 0
    && (state.anchor === undefined || (positiveInteger(state.anchor?.paperId)
      && state.resultIds.includes(state.anchor.paperId) && Number.isFinite(state.anchor.offset)))
    && !!filters && typeof filters === 'object' && !Array.isArray(filters)
    && (filters.sources === undefined || (Array.isArray(filters.sources) && filters.sources.every((source) => typeof source === 'string')))
    && (filters.limit === undefined || positiveInteger(filters.limit))
    && (filters.open_access_only === undefined || typeof filters.open_access_only === 'boolean')
    && (filters.adapt_query === undefined || typeof filters.adapt_query === 'boolean')
    && (filters.source_queries === undefined || (!!filters.source_queries && typeof filters.source_queries === 'object'
      && !Array.isArray(filters.source_queries) && Object.entries(filters.source_queries).every(([source, query]) =>
        ['arxiv', 'openalex', 'crossref', 'semantic_scholar', 'fixture'].includes(source)
        && typeof query === 'string' && query.trim().length > 0 && query.length <= 500)))
    && (filters.mode === undefined || ['auto', 'precise', 'discovery'].includes(filters.mode));
}

export class SearchWorkspaceStore {
  private entries: Entry[] = [];
  private expiredEntry: Entry | null = null;
  private generation = 0;
  notice: string | null = null;
  constructor(private storage?: StoragePort, private now = Date.now) {
    if (!storage) this.notice = '浏览器存储不可用：现场只保留在当前页面，刷新后需重新选择论文。';
    try {
      const raw: unknown = JSON.parse(storage?.getItem(KEY) ?? '[]');
      if (Array.isArray(raw)) this.entries = raw.filter((entry): entry is Entry =>
        typeof entry?.key === 'string' && typeof entry.queryIdentity === 'string' && Number.isFinite(entry.savedAt)
        && validState(entry.state)).slice(-10);
      if (!Array.isArray(raw) || this.entries.length !== raw.length) this.notice = '部分检索现场已损坏，已忽略；请重新选择论文。';
    } catch { this.notice = '检索缓存损坏或存储不可用：刷新后需重新选择论文。'; }
  }
  beginRequest() { return ++this.generation; }
  isCurrent(request: number) { return request === this.generation; }
  load(scope: SearchScope, sessionId?: number): SearchWorkspace | null {
    const entry = [...this.entries].reverse().find((item) => item.key === identity(scope) && (sessionId === undefined || item.state.sessionId === sessionId));
    if (!entry) return null;
    if (this.now() - entry.savedAt >= TTL || this.now() < entry.savedAt) {
      this.expiredEntry = { ...entry, state: structuredClone(entry.state) };
      this.notice = '检索现场已过期（最多保留 24 小时），请重新确认筛选与选文；历史来源状态不代表当前可用。';
      return null;
    }
    return structuredClone(entry.state);
  }
  loadExpired(scope: SearchScope, sessionId?: number): SearchWorkspace | null {
    const entry = this.expiredEntry;
    if (!entry || entry.key !== identity(scope) || (sessionId !== undefined && entry.state.sessionId !== sessionId)) return null;
    return structuredClone(entry.state);
  }
  save(scope: SearchScope, state: SearchWorkspace) {
    if (!validState(state)) return;
    const key = identity(scope);
    // Reconstruct the allowlisted payload rather than persisting caller extensions.
    const safe: SearchWorkspace = {
      query: state.query, filters: {
        sources: state.filters.sources, limit: state.filters.limit,
        open_access_only: state.filters.open_access_only, mode: state.filters.mode,
        adapt_query: state.filters.adapt_query,
        source_queries: state.filters.source_queries ? { ...state.filters.source_queries } : undefined,
      },
      sessionId: state.sessionId, resultIds: [...state.resultIds], selectedIds: [...state.selectedIds],
      page: state.page, scrollY: state.scrollY,
      ...(state.anchor ? { anchor: { paperId: state.anchor.paperId, offset: state.anchor.offset } } : {}),
    };
    const queryIdentity = JSON.stringify([safe.query, safe.filters]);
    this.entries = [...this.entries.filter((item) => !(item.key === key && item.state.sessionId === safe.sessionId)), { key, queryIdentity, state: safe, savedAt: this.now() }].slice(-10);
    try { this.storage?.setItem(KEY, JSON.stringify(this.entries)); } catch { this.notice = '浏览器存储不可用：现场只保留在当前页面，刷新后需重新选择论文。'; }
  }
  saveIfCurrent(request: number, scope: SearchScope, state: SearchWorkspace) {
    if (!this.isCurrent(request)) return false;
    this.save(scope, state);
    return true;
  }
  clear() {
    this.generation++;
    this.entries = [];
    this.notice = this.storage ? null : '浏览器存储不可用：刷新后需重新选择论文。';
    try { this.storage?.removeItem(KEY); } catch { /* Memory was cleared regardless. */ }
  }
  clearNotice() {
    this.notice = null;
    this.expiredEntry = null;
  }
}

export function resolveSearchPosition(state: SearchWorkspace, resultIds: number[], pageSize: number) {
  const index = state.anchor ? resultIds.indexOf(state.anchor.paperId) : -1;
  const page = index >= 0 ? Math.floor(index / pageSize) + 1
    : Math.min(state.page, Math.max(1, Math.ceil(resultIds.length / pageSize)));
  return {
    page, anchor: index >= 0 ? state.anchor! : null,
    notice: state.anchor && index < 0 ? '原定位论文已不可用，已返回可用结果页；请重新确认选文。' : null,
  };
}

function tabStorage(): Storage | undefined {
  try { return window.sessionStorage; } catch { return undefined; }
}
export const searchWorkspace = new SearchWorkspaceStore(tabStorage());
export function resolveSearchTabIdentity(storage: StoragePort | undefined, navigation: string, random: () => string = () => crypto.randomUUID()): string {
  const key = 'rn-search-tab-v1';
  try {
    const prior = storage?.getItem(key);
    // sessionStorage is scoped to one browser tab.  Same-tab route navigation
    // must retain the identity so a detail -> search return can restore its
    // saved session and anchor; a new tab has no prior value to reuse.
    if (prior) return prior;
  } catch { /* An unavailable cache must not block searching. */ }
  const identity = random();
  try { storage?.setItem(key, identity); } catch { /* This module retains the identity in memory. */ }
  return identity;
}
// The tab-scoped storage identity is retained across route navigations and reloads.
const navigation = performance.getEntriesByType?.('navigation')[0] as PerformanceNavigationTiming | undefined;
export const searchTabIdentity = resolveSearchTabIdentity(tabStorage(), navigation?.type ?? 'navigate');
