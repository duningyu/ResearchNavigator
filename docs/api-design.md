# API 设计

## 1. 约定

- Base：`/api`；
- JSON，除 PDF multipart；
- Bearer opaque session token；数据库只保存 SHA-256 token hash；
- OpenAPI：`/docs`、`/openapi.json`；
- 用户数据均通过 current-user dependency 约束。

## 2. 端点

### 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/register` | 注册并签发会话 |
| POST | `/auth/login` | 登录 |
| POST | `/auth/logout` | 撤销当前 token |
| GET | `/auth/me` | 当前用户 |

### 研究档案与项目

`GET/PUT /research-profiles/me`；`POST/GET /projects`；`GET/PUT /projects/{id}`。

### 搜索与论文

| 方法 | 路径 | 状态 |
|---|---|---|
| POST | `/search/papers` | 已实现，多源/去重/provenance |
| GET | `/search/sessions` | 已实现 |
| GET | `/search/sessions/{id}` | 已实现 |
| POST | `/search/sessions/{id}/rerun` | 已实现，按原过滤条件创建新会话 |
| GET | `/papers/{id}` | 已实现 |
| POST | `/papers/{id}/analyze` | 已实现 |
| GET | `/papers/{id}/analysis` | 已实现 |
| POST | `/papers/{id}/upload` | 已实现，multipart + rights confirmation |
| GET | `/papers/{id}/content-status` | 已实现 |
| POST | `/papers/{id}/retrieve` | 已实现 |
| POST | `/papers/resolve` | 已实现；先查本地稳定标识，再查已启用来源 |
| GET | `/papers/{id}/related` | 已实现本地内容相似度；明确不等同引用关系 |
| DELETE | `/documents/{id}` | 已实现；仅上传者可删，清理 FTS 与本地文件 |
| GET | `/papers/{id}/references|citations` | 待具备引用链数据的来源适配器补足 |

### 论文库

`POST/DELETE /library/favorites`；`POST/PUT/DELETE /library/notes`；标签；`PUT /library/papers/{id}/reading-status`；`GET /library`。

### 候选研究空白

| 方法 | 路径 | 关键规则 |
|---|---|---|
| POST | `/gaps/generate` | 建立证据矩阵和候选陈述 |
| POST | `/gaps/{id}/challenge` | 生成查询并保存反向证据候选 |
| POST | `/gaps/{id}/confirm` | challenge 未完成时 409 |
| GET | `/gaps`、`/gaps/{id}` | 用户隔离 |

### 研究计划

`POST /plans` 只接受 confirmed gap；`GET /plans`、`GET /plans/{id}`、`PUT /plan-items/{id}`。

### 推荐与导出

- `POST /recommendations/refresh`：执行透明规则，保存类别、分数、理由和证据；
- `GET /recommendations`：按用户和项目读取持久推荐；
- `GET /workspace/export`：导出当前用户档案、项目、论文库、gap、计划和搜索历史，不包含口令哈希或 token。

### 任务与数据源

`POST /jobs`、`GET /jobs/{id}`、`POST /jobs/{id}/cancel`、`GET /jobs/{id}/events`；worker 实际处理 `noop`、`paper_analysis`、`recommendation_refresh`、`gap_challenge`。数据源端点为 `GET /sources/status`、`POST /sources/{name}/test`。

## 3. 错误码

| HTTP | 语义 |
|---|---|
| 400 | 权利确认缺失、文件输入无效 |
| 401 | 未认证、token 无效/过期 |
| 403 | 已认证但禁止（未来角色权限） |
| 404 | 用户作用域内资源不存在 |
| 409 | 重复注册、非法状态转换、未 challenge 就确认 |
| 422 | Schema、PDF 解析或不支持的任务类型 |
| 429 | 外部源限流（适配器状态中保留） |
| 502/503 | 未来网关/依赖不可用；当前多数源错误以 source status 局部返回 |

错误正文使用 `{"detail":"..."}`。不得回传密钥、完整 token、文件系统敏感路径或原始外部 HTML。

## 4. Schema 版本

分析输出包含 `analysis_version`；评分包含 `score_version`；AgentRun 保存 workflow/prompt/model 版本。接口发生不兼容变化时提高 API major 或引入路径版本，不静默改字段语义。

## 5. 2.2 证据升级、研究卡与评测 API

### 5.1 完整证据工作流

| 方法 | 路径 | 语义 |
|---|---|---|
| POST | `/papers/{paper_id}/evidence-workflows` | 创建版本化证据工作流；不改变旧 `/acquire-evidence` |
| GET | `/evidence-workflows/{job_id}` | 返回 job、终态、最高证据、来源状态和有序事件 |
| POST | `/evidence-workflows/{job_id}/run` | 本地/验收确定性执行；Worker 使用同一 handler |
| POST | `/evidence-workflows/{job_id}/cancel` | 仅 pending/running 可取消 |

恢复性来源失败返回 `partial`，而不是把已有摘要或全文回滚为更低等级。

### 5.2 历史摘要回填

| 方法 | 路径 | 语义 |
|---|---|---|
| POST | `/admin/backfills/abstract-provenance` | 创建 dry-run 或真实回填 job；管理员限定 |
| GET | `/admin/backfills/{job_id}` | 查询状态与分类计数 |
| POST | `/admin/backfills/{job_id}/run` | 执行 DOI→arXiv→严格题名年份重新获取 |
| POST | `/admin/backfills/{job_id}/cancel` | 取消未终止任务 |

迁移后的历史摘要不会直接变可信。只有重新获取、身份严格匹配、来源非 fixture 且 provenance 持久化后才允许 `provides_abstract=true`。

### 5.3 作者、数据集与方向聚类

| 方法 | 路径 | 语义 |
|---|---|---|
| POST | `/papers/{paper_id}/authors/refresh` | 从稳定来源身份刷新作者卡 |
| GET | `/papers/{paper_id}/authors` | 读取作者顺序、身份状态和 provenance |
| POST | `/papers/{paper_id}/datasets/refresh` | 从当前用户可访问分析刷新数据集 mention |
| GET | `/papers/{paper_id}/datasets` | 读取 evidence-bounded 数据集卡 |
| POST | `/projects/{project_id}/direction-clusters` | 对显式论文集合创建版本化确定性聚类 |
| GET | `/direction-clusters/{run_id}` | 读取算法、参数、输入哈希、cluster 与 members |

### 5.4 专家评测

| 方法 | 路径 | 语义 |
|---|---|---|
| GET/POST | `/evaluations/studies` | 列出/创建当前用户拥有的研究 |
| GET | `/evaluations/studies/{study_id}` | 读取冻结协议与任务 |
| POST | `/evaluations/studies/{study_id}/freeze` | 冻结输入和随机种子 |
| POST | `/evaluations/studies/{study_id}/assignments` | 创建盲化 assignment |
| GET | `/evaluations/assignments` | 专家读取自己的任务 |
| POST | `/evaluations/assignments/{id}/start` | 记录开始时间 |
| POST | `/evaluations/assignments/{id}/ratings` | 提交评分与耗时 |
| GET | `/evaluations/studies/{id}/results` | 聚合真实/模拟数量和 claim boundary |

只有真实外部专家评分满足协议后，结果才能进入 `real_expert_results_available`；模拟评分保持独立计数。
