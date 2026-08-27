# ResearchNavigator 2.2.0 科研、产品与工程主张边界

日期：2026-08-28

## 1. 当前可以表述的实现

只有 `delivery/STATUS.json` 对应的当前 checkout 验收为 `PASS` 时，才可以表述为“已验证”。源码与确定性测试支持以下实现范围：

- 多源论文搜索、标准化、去重、实时来源状态和 provenance；
- Discovery/Precise、Top10/20/50、可复现 diversity seed 与经典/前沿候选 composition shortfall；
- 显式 PaperSet、证据级单篇分析、深度论文比较、候选 Gap Explanation、Challenge Search 与真实人工确认 Gate；
- 用户授权 PDF 的上传、解析、切块、检索和删除；
- 兼容的摘要级 `/acquire-evidence` 与新增版本化 `evidence_workflow_v1`；
- DOI/arXiv 身份驱动的 OA 候选解析、许可证/访问策略和 SSRF-resistant PDF fetcher；
- OpenAlex 429 持久 cooldown、rate-limit 元数据和其他来源 fallback；
- 确定性优先、citation-validated 的可选 OpenAI-compatible/Ollama 分析补充，以及 provider/model/prompt/hash/fallback/tool-call 审计；
- 历史摘要 provenance 回填的 dry-run、严格身份匹配、取消、幂等和重新分析；
- 只按稳定 ID 合并的作者卡；
- 由当前用户分析证据生成、缺失字段不补造的数据集卡；
- 保存算法/参数/输入哈希的确定性方向聚类；
- 冻结任务、盲化 assignment、真实/模拟评分分离的专家评测基础设施；
- Docker 冷启动、重启、down/up、备份恢复和 SQLite integrity 的专用验收脚本。

## 2. 证据与全文边界

### 2.1 证据等级

- `metadata_only`：只能陈述元数据；
- `abstract_only`：只能提取摘要实际支持的字段；
- `open_fulltext`、`user_uploaded_fulltext`、`publisher_authorized_fulltext`：只能基于当前可访问内容并保留 page/section/chunk/source citation；
- `unknown` 不能解释为论文没有做；
- `insufficient_evidence` 不能被 LLM 改写成确定事实。

历史 `Paper.abstract` 不因数据库迁移自动变可信。只有重新获取且 DOI/arXiv/严格题名年份身份一致、来源非 fixture、provenance 持久化后，才允许 `PaperSource.provides_abstract=true`。

### 2.2 OA 入口与版权

存在 PDF URL 不代表系统可以自动保存。系统使用四级决策：

- `auto_ingest`：明确许可允许自动摄取；
- `requires_user_confirmation`：有限许可，必须人工确认；
- `link_only`：可访问但权利基础不足；
- `rejected`：登录、付费墙、机构代理、私网、无效 URL 或策略拒绝。

未知 license 不会自动进入全文管线。系统不绕过认证、学校代理、robots 控制或付费墙；不把 HTML 登录页当 PDF；不默认 OCR。

### 2.3 LLM 补充

LLM 不是 source of truth。确定性分析先执行，Provider 只能补充仍为 unknown 且有当前论文可访问 citation 的字段。无效 JSON、跨论文/跨 chunk 引用、摘要越界、Provider 超时或错误会保留确定性结果并写 `fallback_reason`。

字段引用校验证明“输出指向了本地可访问文本”，不自动证明语义蕴含、论文事实正确或模型判断正确。真实 Provider 连通性、费用、延迟和稳定性必须单独验证。

## 3. 作者、数据集与方向聚类边界

- 作者只按 ORCID/OpenAlex/Semantic Scholar 等稳定标识符合并；仅同名时保持 `unresolved`；
- 没有 CRediT 声明时不猜测个人贡献；
- 摘要只提到数据集名称时，数据集卡不能展示未出现的切分、样本量、许可证或官方 URL；
- `direction-cluster-v1` 是确定性文献组织工具，不是学术领域的客观分类，也不证明方向相同或不同；
- 聚类标签来自当前输入文本与参数版本，不能写成学界正式 taxonomy。

## 4. 候选研究空白边界

GapCandidate/GapExplanation 只是在用户显式选择的论文、当前方向快照、查询式、来源和可访问证据范围内形成的候选假设。

禁止写：

- “证明该问题从未被研究”；
- “Agent 发现了确定创新点”；
- “Gap 置信度等于论文创新概率”。

允许写：

> 在本次选定论文集合和检索范围内，直接证据较少，形成需要 Challenge Search、扩展检索和专家确认的候选研究空白。

## 5. 专家评测边界

评测页面、数据库和盲化协议仅证明**评测基础设施已实现**。`is_simulated=true`、LLM judge 或开发者自评不能设置真实专家成功状态。

在真实外部专家按冻结协议提交前：

```text
expert_outcome_validation = awaiting_real_experts
```

不能写“已由专家验证有效”“显著提升科研选题质量”或任何虚构专家人数/收益。

## 6. 环境依赖主张

以下门必须在当前 checkout 真实执行才能标 PASS：

- `uv sync --frozen --extra dev`；
- Ruff、Mypy、完整 backend pytest；
- dependency-aware TypeScript typecheck、Vitest、Vite build；
- Playwright 浏览器闭环；
- official MCP SDK stdio；
- Docker Compose cold start/restart/down-up/restore persistence；
- 实时 OpenAlex/Crossref/arXiv/Semantic Scholar；
- 真实 OpenAI-compatible/Ollama Provider；
- 真实专家效果验证。

fixture、mock、源码存在或历史日志不能替代当前运行。缺少 Docker、node_modules、网络、合法 API key 或真实专家时必须记录 `BLOCKED`/`SKIPPED`，不能写 PASS。

## 7. 产品效果非主张

当前包不能据此声称：

- 已提升研究创新质量或论文录用率；
- 比 Elicit、Consensus、ResearchRabbit、Connected Papers 等更准确；
- 已减少科研时间某个百分比；
- 已形成生产级公网 SaaS、企业级安全或完整商业数据库集成；
- OpenAlex 在所有环境稳定可用；
- 所有 OA 全文都可合法自动保存。

## 8. 推荐简历表述

> 设计并实现 ResearchNavigator 2.2 证据驱动科研工作台：在显式论文集合、证据级分析、论文对比、候选研究空白与人工确认闭环之上，增加合法 OA 候选解析与安全 PDF 摄取、OpenAlex 限流降级、确定性优先的 citation-validated LLM 补充、作者/数据集研究卡、确定性方向聚类、历史证据回填和盲化专家评测基础设施；通过 FastAPI、React、SQLite/FTS5、Worker、MCP 与 HTTP-first/Docker Harness 保留用户隔离、provenance、幂等和科研主张边界。

该表述仍需附上当前 `delivery/STATUS.json`：任何 Docker、浏览器、实时来源、真实 LLM 或真实专家未通过项必须明确说明。
