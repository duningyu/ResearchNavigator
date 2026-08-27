# MCP 设计

## 1. 定位

MCP 是工具接入层，不是论文分析本身。所有工具通过本地 API 继承认证、用户隔离、证据和版权控制。凭据不作为工具参数暴露给模型，而由环境变量提供。

## 2. Server

### scholarly-search

`search_papers`、`get_paper_metadata`、`get_related_papers`、`get_references`、`get_citations`、`search_authors`、`get_author_profile`、`source_health_check`。

当前 search/metadata/source health 连接已实现 API；引用、作者和相关论文若 API 尚未提供，会返回明确 `unavailable`，不得伪装数据。

### paper-access

`resolve_doi`、`resolve_arxiv`、`check_open_access`、`fetch_open_fulltext`、`parse_uploaded_pdf`、`get_content_status`、`delete_local_document`。

- DOI/arXiv 仅解析规范链接，不表示已获得全文；
- 上传路径受 `RN_MCP_ALLOWED_UPLOAD_ROOT` 限制；
- 必须 `rights_confirmed=true`；
- 不允许任意 URL 下载或 SSRF；
- 删除端点不可用时返回 unavailable，不删除远端内容。

### research-workspace

项目、研究档案、收藏、笔记、阅读状态、gap、确认、计划、计划项和导出。

## 3. 运行

```bash
export RN_API_BASE_URL=http://127.0.0.1:8000/api
export RN_MCP_ACCESS_TOKEN='<user-scoped opaque token>'
python -m mcp_servers.scholarly_search.server
```

正式运行要求官方 `mcp[cli]>=2,<3`。`mcp_servers.compat` 的 fallback 仅用于无网络环境的源码合同测试，调用 `run()` 会失败，不得写成 SDK 已验证。

## 4. 工具合同

- Python 类型注解生成 JSON Schema；
- API client 10 秒 connect / 30 秒普通超时，上传 60 秒；
- HTTP 非 2xx 显式抛错或返回 unavailable；
- provenance 保留在 API 响应；
- 用户 token 不写日志；
- 每个工具有 docstring 和 smoke contract test。

## 5. 待补足

- 在联网环境安装官方 SDK 并运行 stdio initialize/list_tools/call_tool 集成测试；
- 为引用、作者、相关论文和导出补齐 API；
- 工具调用持久写入 `tool_calls` 独立表（当前通过 AgentRun/Job 部分审计）；
- 源级速率限制和结构化错误码。
