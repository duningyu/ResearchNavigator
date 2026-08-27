# ResearchNavigator 2.2.0 Page—API—Storage—Evidence 需求追踪矩阵

日期：2026-08-28  
当前验收目录：

`codex_audit/runs/20260827T191732Z_RN220_FINAL/`


## 状态语义

- `PASS`：当前 checkout 的命令和断言已经执行并通过；
- `PARTIAL`：较窄合同通过，但完整环境或真实效果门未通过；
- `BLOCKED`：当前环境缺可执行文件、依赖、网络、合法凭据、Docker、浏览器或真实专家；
- `SKIPPED`：明确不在授权范围；
- `NOT_IMPLEMENTED`：无生产实现。

fixture、mock、源码存在和历史 2.1 日志不能替代 2.2 当前环境 PASS。

## 完整追踪矩阵

| 页面/能力 | 页面/入口 | API | 数据表/存储 | 当前验收证据 | 状态 |
|---|---|---|---|---|---|
| 注册/登录/退出 | `AuthPage`, `AppShell` | `/auth/register|login|logout|me` | `users`, `session_tokens` | full backend pytest | PASS |
| 研究档案/项目 | `ProfilePage`, `ProjectsPage` | `/research-profiles/me`, `/projects*` | `research_profiles`, `research_projects` | full backend pytest | PASS |
| Discovery/Precise Top10/20/50 | `SearchPage` | `POST /search/papers` | `search_sessions`, `papers`, `paper_sources` | search/ranking tests | PASS |
| 搜索会话、seed 与分页 | `SearchPage` | `/search/sessions*` | `diversity_seed`, `composition_json`, result IDs | backend tests；UI syntax only | PARTIAL |
| 来源主动测试与实时来源状态 | `SourcesPage` | `/sources/status`, `/sources/{name}/test` | `source_requests`, `source_runtime_states` | adapter/runtime tests；live DNS unavailable | PARTIAL |
| OpenAlex 429 cooldown/fallback | Sources/Search | search service | `source_runtime_states` | rate-limit/runtime tests | PASS |
| OpenAlex 当前实时可用性 | Sources/Search | live OpenAlex | live provenance report | current live smoke DNS failure；无 key | BLOCKED |
| 论文详情与原始来源 | `PaperPage` | `GET /papers/{id}` | `papers`, `paper_sources` | backend tests | PASS |
| 兼容摘要补证 | `PaperPage` | `POST /papers/{id}/acquire-evidence` | `agent_runs`, `tool_calls`, `source_requests`, `provides_abstract` | evidence-acquisition tests | PASS |
| 完整证据工作流 | `EvidenceWorkflowPanel` | `POST /papers/{id}/evidence-workflows`, `GET/POST /evidence-workflows/{job_id}/*` | `jobs`, `job_events`, analysis/doc provenance | workflow + worker tests | PASS |
| 证据工作流进度 UI | `PaperPage` | 同上 | 同上 | frontend syntax/source contract；无 dependency-aware browser run | PARTIAL |
| OA 候选解析/权利策略 | `PaperPage` | workflow internal | OA candidate/provenance | resolver/policy tests | PASS |
| 远程 PDF SSRF/redirect/MIME/magic/size | workflow | workflow internal | `paper_documents` provenance columns | remote fetcher security tests | PASS |
| 合法 OA PDF 复用解析索引 | `PaperPage` | workflow | `paper_documents`, `paper_chunks`, FTS5 | OA ingestion/workflow tests | PASS |
| 真实 OA 全文获取 | `PaperPage` | live OA sources | downloaded lawful content | current environment DNS/rights prerequisite unavailable | BLOCKED |
| PDF 上传/解析/检索/删除（用户授权） | `PaperPage` | upload/list/retrieve/delete | uploads, documents, chunks, FTS5 | PDF integration tests | PASS |
| 确定性结构化分析 | `PaperPage` | analyze/read | `paper_analyses` | analysis/rag tests | PASS |
| LLM citation-validated 补充 | `PaperPage` | analyze/read | analysis provider fields, `agent_runs`, `tool_calls` | unit + API provider/fallback tests | PASS |
| 真实 LLM Provider | `PaperPage` | external provider | provider audit | provider/key 未配置 | BLOCKED |
| 分析状态、missing 与 fallback UI | `PaperPage` | analysis/workflow | analysis JSON | frontend syntax/source contract | PARTIAL |
| 历史摘要 dry-run/回填/取消 | `AdminPage` | `/admin/backfills/abstract-provenance`, `/admin/backfills/{id}/*` | jobs/events, paper sources, new analysis | backfill tests + Admin contract | PASS |
| 历史数据实际回填数量 | `AdminPage` | 同上 | 当前用户运行库 | 未对真实历史运行库执行 | BLOCKED |
| 作者卡 | `PaperIntelligenceCards` | `/papers/{id}/authors`, `/authors/refresh` | `authors`, `paper_authors`, `author_source_records` | author identity/API tests | PASS |
| 数据集卡 | `PaperIntelligenceCards` | `/papers/{id}/datasets`, `/datasets/refresh` | `dataset_cards`, `paper_dataset_mentions` | dataset evidence tests | PASS |
| 作者/数据集卡浏览器 UI | `PaperPage` | 同上 | 同上 | syntax/source contract；无 current Playwright | PARTIAL |
| 方向聚类 | `DirectionMapPage` | `POST /projects/{id}/direction-clusters`, `GET /direction-clusters/{run_id}` | direction cluster run/cluster/member | deterministic/user-scope tests | PASS |
| 方向聚类浏览器闭环 | `DirectionMapPage` | 同上 | 同上 | syntax/source contract；无 current Playwright | PARTIAL |
| 专家研究/盲化任务/评分 | `EvaluationsPage` | `/evaluations/studies*`, `/evaluations/assignments*` | evaluation study/task/assignment/rating/result | expert evaluation tests | PASS |
| 模拟评分不升级真实验证 | `EvaluationsPage` | results | evaluation result status | simulated-boundary test | PASS |
| 真实专家效果验证 | `EvaluationsPage` | same | real expert ratings | 无真实外部专家 | BLOCKED |
| 收藏/笔记/标签/阅读状态 | `LibraryPage`, `PaperPage` | `/library/*` | favorites, notes, tags, status | backend tests | PASS |
| 显式 PaperSet | library/compare/gap | `/paper-sets*` | paper sets/items | backend tests | PASS |
| 深度论文对比 | `ComparePage` | `/comparisons*` | comparison runs | backend tests；browser not rerun | PARTIAL |
| Gap Explanation/Challenge/Human Gate（默认不执行 `simulated_human_confirmation`） | `GapsPage` | `/gaps*` | gap candidates/evidence/explanations | backend tests；browser not rerun | PARTIAL |
| 研究计划 | `PlansPage` | `/plans*` | plans/items | backend tests | PASS |
| Jobs 终态/任务取消/重试 | `JobsPage` | `/jobs*` | jobs/events | worker/job tests；`partial` terminal contract | PASS |
| Settings/Admin 安全状态 | `SettingsPage`, `AdminPage` | settings, config-status, runtime-config | settings + whitelist config | admin/security tests | PASS |
| 备份恢复/导出 | Backup/Workspace | backup/stage-restore/export | backup ZIP, pending restore, DB/files | backend roundtrip tests | PASS |
| HTTP-first 验收语义 | Harness | public API | API-owned state | acceptance tests | PASS |
| 幂等/场景版本 | Harness/mutations | headers | `idempotency_records` | idempotency tests | PASS |
| Alembic 0001→0005 | — | — | 53-table schema, FTS5 | explicit upgrade + integrity log | PASS |
| FastAPI 路由唯一性/OpenAPI | — | 83 paths | — | route uniqueness test + OpenAPI export | PASS |
| 响应式导航与 2.2 UI 源码 | all Web | — | — | 41 TS/TSX syntax transpile | PASS（syntax only） |
| TypeScript/Vitest/Vite | all Web | — | — | node_modules/pnpm unavailable; Corepack DNS failure | BLOCKED |
| Playwright 浏览器闭环 | all Web | public API | full state | current 2.2 browser dependencies unavailable | BLOCKED |
| MCP Python 合同 | MCP source | MCP→HTTP | API state | backend contract/smoke tests | PASS |
| Official MCP stdio | MCP clients | official SDK | API state | `mcp` package unavailable; uv sync DNS blocked | BLOCKED |
| Docker Compose 静态/脚本合同 | API/Worker/Web | all | isolated runtime | Docker contract tests | PASS |
| Docker cold start/restart/down-up/restore | API/Worker/Web | all | bind runtime | Docker executable absent | BLOCKED |
| Ruff/Mypy | backend | — | — | executables unavailable because frozen sync blocked | BLOCKED |
| Web of Science/Elsevier/Scopus | — | — | — | no lawful credentials/contract scope | SKIPPED |

## 关键边界

1. OA implementation PASS 不等于任意论文都能合法自动保存；未知 rights 保持 `link_only/rejected`。
2. OpenAlex fallback PASS 不等于 OpenAlex 实时来源 PASS。
3. Mocked/citation-validation Provider tests PASS 不等于真实 LLM endpoint PASS。
4. 专家评测基础设施 PASS 不等于真实专家效果验证 PASS。
5. `frontend_syntax` 只证明 TS/TSX 可转译，不替代 dependency-aware typecheck、Vitest、Vite 或 Playwright。
6. Docker 脚本存在与 contract tests PASS 不替代真实容器冷启动和持久性运行。

