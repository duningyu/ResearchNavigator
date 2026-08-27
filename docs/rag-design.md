# RAG 与证据设计

## 1. 语料边界

允许：公开摘要、合法开放全文、用户确认有权使用的 PDF、授权 API 全文、用户笔记。

禁止：绕过权限全文、截断搜索片段冒充全文、模型根据标题生成“伪全文”。

## 2. Evidence Level

- `metadata_only`；
- `abstract_only`；
- `open_fulltext`；
- `user_uploaded_fulltext`；
- `publisher_authorized_fulltext`。

摘要级禁止抽取正文参数、实验设置、作者 Future Work 和正文局限。缺失字段返回“未在当前可访问文本中找到”或 `missing_fields`，不能补齐。

## 3. 摄取

1. 用户勾选权利确认；
2. 安全文件名、`.pdf`、MIME、`%PDF` magic、大小限制；
3. PyPDF 按页解析；
4. 基于页和段落切块；
5. 保存 section、page、chunk index、text hash、source/evidence/version；
6. 写入 FTS5 和确定性 hashing vector。

当前 parser 不使用 OCR。扫描型 PDF 应返回解析不足，而不是自动声称全文已读。

## 4. 检索

- lexical：FTS5/BM25；
- dense：固定哈希维度向量 + cosine；
- hybrid：归一化 lexical/dense 加权；
- top-k：请求可配且有限；
- 结果：chunk_id、text、section、page、两类分数、evidence level。

确定性向量用于离线与测试可复现，不等同于语义 embedding。替换为真实 embedding 时需增加版本、重建索引和 parity/evaluation。

## 5. 结构化分析

`PaperAnalysisOutput` 使用 Pydantic：summary、problem、task、methods、datasets、metrics、Future Work、limitations、citations、missing fields 和 warnings。

当前实现为保守确定性抽取。可选 LLM Provider 必须：

- 输入只含检索证据；
- 输出满足 JSON Schema；
- 每个重要字段带 citation；
- 运行 citation validator；
- 失败时不覆盖已验证结果；
- 保存 prompt/model/version。

## 6. 引用校验

每个 citation 必须属于当前用户可访问文档或论文摘要；page/chunk 必须存在；引用文本应支持所述字段。不能只显示论文标题作为“引用”。

## 7. 评价集

固定开放论文 fixture（真实开放论文与测试 fixture分开）包括：

- 可明确抽取的问题、方法、数据集；
- 明确 Future Work/Limitations；
- 明确不存在的字段；
- 摘要级和全文级对照；
- 解析失败 PDF。

指标：Retrieval Hit Rate、Citation Precision/Coverage、Faithfulness、Structured Extraction Accuracy、Missing-field refusal accuracy、PDF parsing failure rate。分模型、证据等级和论文结构报告。

## 2.2 分层分析与证据升级

全文摄取仍复用既有 `validate → parse → chunk → FTS5/hash-vector index` 管线。新增 OA 获取层只负责候选、权利策略和安全下载，不另建第二套解析语义。

分析顺序固定为：

1. 根据可信摘要或当前用户可访问 chunks 构造 evidence snapshot；
2. 执行确定性 `structured` 提取并生成字段级 citation；
3. 若配置 Provider，再对 unknown 字段执行受限补充；
4. 校验每个非空字段的本地 citation、paper/user scope 和 evidence-level eligibility；
5. 合并合格字段，拒绝越界字段，并持久化 provider/output/fallback audit；
6. 由最终分析刷新数据集 mention 等派生对象。

LLM 结果不能覆盖已有确定性证据，也不能把摘要级 evidence 解释成全文协议。`fallback_reason` 是正常降级结果，不等于整次分析失败。
