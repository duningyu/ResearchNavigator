# ResearchNavigator（研途智选）设计规格

## 1. 目标

构建面向研究生的证据驱动科研选题与论文研究工作台，覆盖研究方向建档、多源论文检索、论文结构化理解、可解释匹配与复现评分、候选研究空白、反证检索、研究计划和本地持久化。

## 2. 已批准范围

本规格以 `docs/APPROVED_MASTER_PROMPT.txt` 为最高产品需求来源。实现采用两级交付：

- V1：论文发现、个人论文库、PDF/RAG、评分、研究计划、SQLite 持久化。
- V2：研究方向分解、证据矩阵、候选研究空白、challenge search、人工确认、可审计工作流。

## 3. 架构

- 前端：React + TypeScript + Vite + Ant Design。
- API：FastAPI + Pydantic + SQLAlchemy + SQLite WAL。
- Worker：数据库轮询任务执行器，不引入 Redis。
- 检索：开放数据源 Adapter；SQLite FTS5 BM25 + 本地 hashing dense vector 混合召回。
- RAG：仅使用公开摘要、合法开放全文、用户授权上传 PDF；所有结论带 evidence level 和 citation locator。
- MCP：三个 stdio MCP Server，分别封装 scholarly search、paper access、research workspace。
- 部署：Docker Compose；数据库、上传、索引和备份目录全部挂载。

## 4. 关键边界

- 不宣称自动证明研究空白或绝对创新。
- abstract_only 不输出摘要之外的具体方法、参数或 Future Work。
- 未接通的授权数据源必须显示 `not_configured`。
- fixture/mock 与真实外部结果必须保留来源标签。
- 用户收藏、笔记、计划和研究项目按 user_id 隔离。

## 5. 验收口径

交付包含可运行代码、测试、文档、Docker 配置、种子数据、Codex 审计 prompt、哈希清单和已知限制。无法在当前执行环境验证的 Docker 冷启动、浏览器 E2E 和真实外部 API 联网测试，必须标记为 `NOT_RUN`，不得写成通过。
