# 数据源合同

## 1. 统一接口

每个适配器实现：

```python
async def search(request: SearchRequest) -> AdapterSearchResult
async def health() -> SourceStatus
```

输出 `PaperRecord`，保留 `SourceProvenance(source, source_id, source_url, fetched_at, raw_hash, is_fixture)`。

## 2. 当前适配器

| 源 | 默认 | 授权 | 主要 ID | 降级 |
|---|---|---|---|---|
| Fixture | 开发可选；生产应关 | 无 | fixture ID | 显式 `is_fixture=true` |
| OpenAlex | 开 | 开放 API/礼貌池 | OpenAlex ID、DOI | 单源 error，其他源继续 |
| Crossref | 开 | 开放 REST；建议 mailto | DOI | 无摘要时 metadata_only |
| arXiv | 开 | 开放 API，遵守速率 | arXiv ID | XML/网络错误局部报告 |
| Semantic Scholar | 开 | Key 可选/额度相关 | Corpus/Paper ID | 429 标记 rate_limited |
| Unpaywall | 预留 | 需要邮箱 | DOI | 未实现显示 disabled/not_configured |
| Web of Science | 关闭 | 学校/机构授权 | WoS ID | 不模拟登录 |
| ScienceDirect/Scopus | 关闭 | Elsevier Key/订阅 | PII/Scopus ID | 不绕过付费墙 |

## 3. 字段映射优先级

- 标题：源原文，另存 normalized title；
- DOI：去 URL 前缀、转小写；
- arXiv：去 `arXiv:` 前缀；
- 日期：保留可解析日期，否则只保留年份；
- 作者：姓名 + 源作者 ID/ORCID，不凭同名自动合并；
- URL：来源页、出版社页、开放 PDF 分开；
- citation count：仅作为来源元数据，不直接作为质量标签；
- raw hash：原始记录规范序列化后的 SHA256（源支持时）。

## 4. 去重

1. DOI；2. arXiv ID；3. 其他稳定 ID；4. 标准化标题+年份；5. 标题模糊相似只生成候选，不静默合并。

## 5. 超时、重试和限流

适配器使用有限超时。当前联邦服务不做无限重试，避免多源雪崩。生产补足应采用带抖动的 429/5xx 有界重试、源级并发限制和缓存，并在 source status 中记录实际结果。

## 6. 版权与全文

元数据/摘要许可不自动等于全文许可。开放 PDF 或用户上传全文进入文档管线；授权出版社全文必须单独实现并记录 `publisher_authorized_fulltext`。登录页、错误页和任意 HTML 不得当 PDF。

## 7. 2.2 OA 解析合同

完整证据工作流可从 DOI/arXiv 身份查询 OA 候选，但候选必须包含来源、稳定 ID、landing URL、PDF URL、license、host/version、provenance hash 和 access decision：

- `auto_ingest`：明确允许自动保存和解析的许可；
- `requires_user_confirmation`：有限许可，需要用户再次确认用途；
- `link_only`：可访问但无法证明允许系统保存；
- `rejected`：付费墙、登录、代理、私网、无效 URL 或其他策略拒绝。

“能下载”不等于“可以自动摄取”。Crossref link、未知 license 或出版社入口不能单独支持 `auto_ingest`。

## 8. OpenAlex 429 与持久冷却

OpenAlex adapter 支持服务端 API key，并解析可获得的 rate-limit headers。HTTP 429/受限响应写入 `source_runtime_states`，设置有界指数 cooldown；cooldown 内请求不打到网络，联邦检索继续调用其他来源。UI 显示 `rate_limited/degraded`、恢复时间和 key 配置布尔值，但永不返回 key。OpenAlex 实时可用性必须单独验收，其他来源成功不能把它标为 PASS。

## 9. 安全 PDF 获取

所有重定向跳转都重新校验 scheme、DNS 和 IP；禁止私网、回环、链路本地、保留地址、URL 用户凭据、浏览器 cookie 和机构代理 session。下载流式限长，并同时验证响应 MIME 与 `%PDF-` 文件头；HTML 登录页、超大内容或无可提取文本分别记录明确失败码，不静默提升 evidence level，也不默认 OCR。
