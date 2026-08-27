# 研途智选（ResearchNavigator） 2.2

面向研究生和科研初学者的**证据驱动科研选题与论文研究工作台**。系统把研究方向档案、多源论文检索、证据级论文理解、方向匹配、复现评估、候选研究空白、反证检索、人工确认和研究计划连接成一条可审计流程。

> 边界：候选研究空白不是创新性证明；摘要级证据不得被扩写成全文细节；fixture 只用于离线流程测试。

## 当前包包含

- FastAPI + SQLAlchemy + SQLite/FTS5 后端；
- React + TypeScript + Ant Design 前端源码；
- OpenAlex、Crossref、arXiv、Semantic Scholar 与显式 fixture 适配器；
- 用户注册登录、研究档案、项目、检索、去重、论文详情、收藏、笔记、标签、阅读状态；
- 用户确认版权后的 PDF 解析、分页切块、FTS5 + 确定性稠密向量混合召回；
- Discovery/Precise 检索模式、Top10/20/50、search-session 固化排序与可复现 diversity seed；
- 显式 PaperSet：对比/候选空白必须使用用户选择的论文集合与项目/方向快照，不再默认“上一次搜索”；
- evidence level 约束下的深度结构化分析（研究问题、任务、理论/方法创新、研究路线、I/O、数据集、baseline、指标、协议、结果、Future Work、局限等）、可解释方向匹配度与复现推荐度；
- 证据级论文对比矩阵；
- bounded Gap Explanation + Challenge Search + 真实人工确认门；
- 阅读、复现、数据准备、最小实验和失败退出计划；
- SQLite 持久任务与 worker，实际执行论文分析、推荐刷新和 gap challenge；
- 三个 MCP stdio Server 源码；
- 搜索会话重跑、论文解析/本地相关论文、透明持久推荐、文档删除与用户工作区导出；
- Settings、管理员安全运行配置、Jobs 终态/取消、来源主动测试、SourceRequest provenance 审计；
- 版本化 `evidence_workflow_v1`：身份解析、可信摘要补充、OA 入口发现、许可证策略、远程 PDF 安全获取、全文解析、确定性分析、可选 LLM 补充和派生研究卡刷新；
- 合法 OA 候选解析与四级策略：`auto_ingest`、`requires_user_confirmation`、`link_only`、`rejected`；未知许可证不会自动摄取；
- OpenAlex 持久冷却、429 退避和多来源降级；OpenAlex 失败不会阻断 Crossref、arXiv 或 Semantic Scholar；
- 确定性优先的 LLM 分析补充，字段必须绑定本地 citation；无效输出、越界字段或 Provider 失败回退到确定性结果；
- 来源可追溯的作者卡、证据约束的数据集卡、确定性方向聚类，以及不把模拟评分冒充真实专家结论的盲评基础设施；
- 管理员历史摘要可信回填：默认 dry-run，只有 DOI/arXiv/严格题名年份重新获取成功且 provenance 合格时才提升；
- HTTP-first 验收场景、幂等键/场景版本、worker terminal-state 验收；
- Docker Compose、备份/恢复/导出、Alembic、PRD、TechDocs、OpenAPI、测试和 Codex 审计 Harness。

## 快速启动：Docker（推荐）

```bash
cp .env.example .env
# 生产或局域网使用前，关闭 fixture：RN_ENABLE_FIXTURE_SOURCE=false
docker compose -f infra/docker-compose.yml up --build
```

访问：

- Web：`http://127.0.0.1:8080`
- API：`http://127.0.0.1:8000/api/health`
- OpenAPI：`http://127.0.0.1:8000/docs`

局域网同组成员使用 `http://主机局域网IP:8080`。Windows 防火墙或 macOS 防火墙需要允许 8080 端口。默认不建议暴露到公网。

## 原生开发

### 后端

```bash
uv sync --extra dev
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
export PYTHONPATH="$PWD/apps/api:$PWD"
cp .env.example .env
uvicorn research_navigator.main:app --reload --host 0.0.0.0 --port 8000
```

另一个终端：

```bash
source .venv/bin/activate
export PYTHONPATH="$PWD/apps/api:$PWD"
python -m services.worker.main --poll-seconds 2
```

### 前端

```bash
cd apps/web
corepack enable
pnpm install --frozen-lockfile
pnpm run dev -- --host 0.0.0.0
```

开发访问 `http://127.0.0.1:5173`。Vite 将 `/api` 代理到 `http://127.0.0.1:8000`。

## 测试

```bash
pytest -q
ruff check apps/api services mcp_servers scripts tests
mypy apps/api/research_navigator services mcp_servers
PYTHONPATH=apps/api:. python scripts/export_openapi.py --output delivery/OPENAPI.json

cd apps/web
pnpm run typecheck
pnpm test
pnpm run build
RN_E2E_BASE_URL=http://127.0.0.1:8080 pnpm run test:e2e
```

外部 API 集成测试与 fixture/mock 测试必须分开。`scripts/verify_live_sources.py` 只验证实时来源状态、稳定标识符与 provenance hash，不固定未来返回标题/数量。授权源没有凭据时应显示 `not_configured` 或 `disabled`，不能伪装通过。

当前交付环境不能执行的门必须记录为 `BLOCKED`，明确不在范围的授权源记录为 `SKIPPED`；源码存在不等于验收 PASS。Docker 冷启动、浏览器闭环、实时 OpenAlex、真实 LLM Provider 与真实专家效果验证必须分别执行，不能由 fixture 或后端单测替代。

## 数据持久化

运行状态默认在 `runtime/`：

- `research_navigator.db`：SQLite；
- `uploads/`：用户确认有权使用的 PDF；
- `vector_index/`：预留的本地向量状态；
- `backups/`：备份 ZIP。

```bash
PYTHONPATH=apps/api:. python scripts/backup.py
# CLI restore 只应在服务已停止时使用；会先在临时目录校验路径、manifest、hash 与 SQLite integrity
PYTHONPATH=apps/api:. python scripts/restore.py runtime/backups/<backup>.zip --force
PYTHONPATH=apps/api:. python scripts/export_workspace.py --email user@example.com --output exports/user.json
```

## 演示账户

演示账户不会自动创建。开发环境可执行：

```bash
PYTHONPATH=apps/api:. python scripts/seed_demo.py \
  --email demo@research-navigator.local \
  --password 'replace-with-a-local-password'
```

fixture 论文均带 `is_fixture=true`，其中合成论文标题不得用于科研结论、简历指标或论文证据。

## MCP

安装官方 MCP Python SDK v2 后运行：

```bash
export RN_API_BASE_URL=http://127.0.0.1:8000/api
export RN_MCP_ACCESS_TOKEN='<登录后取得的用户会话 token>'
python -m mcp_servers.scholarly_search.server
python -m mcp_servers.paper_access.server
python -m mcp_servers.research_workspace.server
```

MCP 仅作为工具接入层。论文证据边界、授权和用户隔离仍由 API 执行。

## 文档入口

- [PRD](docs/PRD.md)
- [TechDocs 索引](docs/TECHDOC_INDEX.md)
- [架构](docs/architecture.md)
- [RAG 设计](docs/rag-design.md)
- [候选研究空白方法](docs/research-gap-method.md)
- [科研主张边界](docs/claim-boundary.md)
- [需求追踪矩阵](docs/requirement-traceability.md)
- [部署手册](docs/deployment-runbook.md)
- [Codex 审计指令](CODEX_AUDIT_AND_COMPLETION_PROMPT.md)

## 已知限制

以 `delivery/STATUS.json` 和 `docs/claim-boundary.md` 为准。特别是：

- 确定性分析仍是默认和回退路径；可选 LLM 补充必须通过字段级 citation 校验，但该校验仍不是语义蕴含或事实正确性的自动证明；
- Web of Science、ScienceDirect/Scopus 仅有授权边界设计，未接入真实凭据；
- MCP SDK 在无网络构建环境可能无法安装，代码不会将 fallback 冒充正式 stdio 运行；
- dependency-aware 前端 typecheck/Vitest/build、Playwright、MCP stdio、Docker、真实开放 API 连通性只有当前环境实际执行后才可标 PASS；
- 作者卡不会仅凭姓名合并作者；数据集卡不会从名称补造许可证、切分或样本量；方向聚类只是文献组织结果，不是客观学科分类；
- 专家评测页面和数据结构不等于真实专家效果验证；没有真实外部专家评分时状态保持 `awaiting_real_experts`；
- 研究空白只能作为带检索边界的候选，必须经反证检索和专家确认。
