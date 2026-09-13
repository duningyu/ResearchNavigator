# ResearchNavigator R3 — Open Evidence Cache + 中文证据工作台

## Purpose

R3 reduces the cost of supplying evidence for a paper while preserving the evidence boundary established by R2. The implementation is split into three ordered packages: open evidence acquisition and shared caching (R3.1), analysis reuse and orchestration (R3.2), and Chinese quick interpretation UI (R3.3).

## Frozen principles

1. 搜到论文后优先自动寻找合法公开材料，不先要求用户上传 PDF。
2. 同一份允许缓存的公共材料只获取和解析一次，之后复用。
3. 没有全文仍进行摘要级初判，不伪造正文级证据。
4. 前台快速解读默认中文；英文原文仍是 evidence，并可展开查看。
5. 自动化目标是降低用户补材料成本，不是宣称系统知道所有内容。

## Explicit non-goals

- 不做 Sci-Hub、paywall/login 绕过或通用网页爬虫。
- 不做 OCR、GraphRAG、多 Agent、全站预抓取 PDF。
- 不自动宣布“已发现研究空白”。
- 不把机器翻译或中文解释当作 scientific evidence。
- 不创建数据库 migration；复用现有 PaperDocument、分析记录和 JSON 字段。
- 不访问或修改 Production、deploy branch、Production Secret 或 Vercel。

## Evidence and safety contract

Only scholarly-adapter-originated HTTP(S) URLs may enter bounded fetching. The fetcher rejects local/private targets, unbounded redirects, oversized or non-PDF responses, and ambiguous rights. A reachable URL is not permission to cache. Shared durable caching requires an explicitly approved source/license combination; otherwise the workflow falls back to abstract analysis.

Public documents are keyed by paper, shared-user scope, and content hash. Cache hits do not rewrite storage, parse again, or duplicate chunks. Public evidence remains original-language evidence with provenance; Chinese quick interpretation is display-only.

## Acceptance boundary

R3 local acceptance must demonstrate identity-safe acquisition, fail-closed rights and SSRF behavior, shared cache reuse, analysis cache invalidation by material/project/version identity, Chinese-first display with collapsed original evidence, and graceful fallback to abstract-level analysis. Historical plans and analysis records remain unchanged, and Production deployment is explicitly out of scope until review.
