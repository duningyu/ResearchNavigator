# Changelog

## 2.2.3 — 2026-08-30

### Fixed

- Exact DOI requests are now resolved by canonical identifier before broad textual search, with provider fallback.

修复 DOI 被作为普通文本进入宽泛检索，导致已存在论文无法精确解析的问题。

## 2.2.0 evidence platform — 2026-08-28

### Added

- Added additive Alembic `0005` schema for source runtime state, evidence workflow audit, OA document provenance, LLM analysis provenance, author identities, dataset mentions, direction clusters and expert evaluations.
- Added versioned `evidence_workflow_v1` with persistent events, cancellation, worker execution and `succeeded|partial|failed|cancelled` terminal semantics while preserving the older bounded `/acquire-evidence` endpoint.
- Added lawful OA candidate resolution, explicit license/access decisions and a redirect-aware SSRF-resistant PDF fetcher that validates size, MIME, PDF magic and content hash before reusing the existing parser/indexer.
- Added persistent OpenAlex 429 cooldown and multi-source fallback without relabelling OpenAlex itself as healthy.
- Integrated deterministic-first optional OpenAI-compatible/Ollama enrichment with citation validation, secret-free audit persistence and deterministic fallback.
- Added provenance-aware author cards, evidence-bounded dataset cards, deterministic direction clustering, frozen/blinded expert evaluation infrastructure and admin-controlled historical abstract provenance backfill.
- Added UI surfaces for evidence acquisition progress, author/dataset cards, direction clustering, expert evaluations and safe historical backfill.
- Added a dedicated Docker cold-start/restart/down-up/backup-restore persistence harness that reports missing Docker as `BLOCKED`.

### Compatibility and claim boundaries

- Existing clients may continue using `POST /papers/{id}/acquire-evidence`; full acquisition uses additive workflow endpoints.
- Legacy abstracts remain untrusted until they are re-fetched with strict identity matching or a lawful full text is ingested.
- Unknown or ambiguous OA rights never trigger automatic full-text storage.
- Simulated ratings cannot set `expert_outcome_validation` to a real-expert success state.
- Docker, live OpenAlex, live LLM providers, browser E2E and real-expert outcomes require independent current-environment evidence.

## 2.1.1 evidence acquisition patch — 2026-08-28

- Added an audited `POST /papers/{id}/acquire-evidence` workflow and MCP façade for bounded DOI→arXiv→exact-title/year metadata and abstract acquisition.
- Added field-level abstract provenance, explicit production-adapter eligibility, fixture/unverified-abstract abstention, transactional rollback and per-source UI status.
- Added Alembic 0004 and deployed it to the local runtime after a consistent SQLite backup; legacy abstracts remain unverified until reacquired.
- Kept legal OA full-text fetching explicitly `NOT_IMPLEMENTED`; locally uploaded authorized full text bypasses external acquisition.

## 2.1.1 continuation audit — 2026-08-27

- Repaired cross-artifact release metadata and Gap Ledger consistency.
- Added tested OpenAI-compatible and Ollama structured provider transports with bounded retries and credential-safe errors; analysis API/audit integration remains partial.
- Established dedicated `tests/security` and `tests/rag_eval` suites without reducing the full test count.
- Re-audited live sources: Crossref, arXiv and Semantic Scholar passed; OpenAlex remained rate-limited.
- Restored omitted NOT_IMPLEMENTED/PARTIAL product gaps instead of treating environment blockers as the only remaining work.

## 2.1.0 — 2026-08-27

### Added / Changed

- Selection-first PaperSet workflow for paper comparison and candidate gaps; removed implicit newest-search coupling.
- Discovery/Precise search, Top10/20/50, seeded reproducible diversity and auditable classic/frontier candidate composition.
- Evidence-grade analysis UI/fields, PDF lifecycle, deep comparison matrix, bounded Gap Explanation and favorite-to-research workflows.
- Responsive narrow-screen navigation, Settings/Admin/Jobs/Source Test/Backup pages.
- HTTP-first acceptance, worker terminal-state checks, replay idempotency and persisted source-call provenance.
- Safe staged restore and pnpm lockfile-aligned frontend install/build contract.

### Boundaries

- Candidate gaps remain hypotheses, not novelty proof.
- Live-source results are not deterministic fixtures.
- Environment-dependent frontend/Playwright/MCP/Docker gates remain BLOCKED unless executed in the current release run.

## 2.0.0-rc1 — 2026-08-26

### Added

- 候选研究空白证据矩阵、challenge queries、反向证据候选和人工确认状态门；
- 从确认研究问题生成阅读、复现、数据准备、最小实验与风险检查计划；
- AgentRun、Job、JobEvent 持久审计，并接入论文分析、推荐刷新和 gap challenge 处理器；
- 搜索重跑、论文解析、本地相关论文、持久推荐、文档删除和工作区导出 API；
- React 研究工作台页面；
- 三个 MCP Server 工具合同；
- Docker、备份恢复、PRD、TechDocs、Codex Harness。

### Boundaries

- 不将候选空白描述为已证明创新；
- 授权数据源未接入真实凭据；
- 当前沙箱未验证 Docker、MCP SDK 正式启动和前端依赖构建。

## 1.0.0-rc1 — 2026-08-26

### Added

- 本地用户认证、研究档案和项目；
- 多数据源论文搜索、标准化、去重和 provenance；
- 论文库、收藏、笔记、标签、阅读状态；
- 用户授权 PDF 解析和混合检索；
- evidence level 约束的结构化分析；
- 可解释方向匹配与复现评估；
- SQLite WAL、外键和持久化 worker。
# 2.2.1 verification patch — 2026-08-28

- Fixed Direction Map strict TypeScript nullability.
- Corrected ambiguous frontend test selectors and Router test context.
- Revalidated backend, security/RAG, MCP and Alembic gates; external gates remain explicitly blocked or failed.
# 2.2.2 verification closure — 2026-08-28

- Ruff and Mypy are clean.
- Playwright now launches an isolated API/Worker/Web stack with readiness polling and teardown.
- No new product capability; Docker, live LLM and real expert gates remain externally blocked.
