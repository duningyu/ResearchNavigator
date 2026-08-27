# 评价计划

## 1. 原则

- fixture 与真实 API 结果分开；
- 未安装依赖/无网络/无 Docker 标记 NOT_RUN；
- 单次成功不是稳定结论；
- 版本、数据、查询、时间和配置可追踪；
- 不以“生成了多少 gap”作为核心指标。

## 2. 产品指标

首次有效论文时间、搜索→收藏、详情打开、再次访问、计划创建/完成、用户修改率、周留存。按研究阶段和方向分组，避免小样本总体平均误导。

## 3. 检索

构建查询-相关论文评审集；报告 Precision@10、Recall@K、NDCG@10、重复率、单源失败率和 P50/P95 延迟。多源融合与单源分别报告；fixture 不参与真实指标。

## 4. RAG

- Retrieval Hit Rate@K；
- Citation Precision/Coverage；
- Faithfulness；
- Structured Extraction Accuracy；
- Missing-field refusal accuracy；
- 摘要越界率；
- PDF 解析失败率。

对 abstract_only、open_fulltext、user_uploaded_fulltext 分层。

## 5. 方向匹配

建立人工对：高度匹配、相邻任务、关键词相同但输出不同、完全不匹配。评价组成分解释一致性和排序；对比纯 embedding、纯关键词和 LLM 单分数。调整权重只用 validation，冻结后报告 test。

## 6. 复现推荐

人工核验代码、数据、环境、超参、算力、协议、许可。评价状态准确率和 blocking reason precision。unknown 与 missing 混淆率单独报告。

## 7. 候选 Gap

至少两名领域评审者标注：值得进一步查证/被直接既有工作推翻/范围太宽/术语假空白/数据不支撑。报告：

- challenge 前后被推翻比例；
- 专家“值得查证”率；
- 支持/反向证据覆盖；
- 人工修改率；
- inter-rater agreement；
- 生成到计划转化率。

## 8. 工程

后端单元/集成/contract；前端 typecheck/Vitest/build；Playwright；MCP stdio；Docker cold start；空库迁移；重启持久化；备份恢复；密钥扫描；SSRF/路径穿越/越权。

## 9. 时序异常检测示范的科研指标

若用系统辅助当前研究，实验报告仍需 TP/FP/TN/FN、Precision/Recall/F1、PR-AUC/ROC-AUC、预测正例率、异常率、FP/FN per 1000、P@0.5/1/2/5%、事件级、delay/lead time、设备/异常类型、macro/micro、多 seed、bootstrap CI、calibration、memory hit/conflict。该产品不替代实验协议。

## 10. 2.2 专家盲评协议

系统只提供评测基础设施，不自动产生专家效果结论。建议流程：

1. 冻结论文、baseline/candidate 版本、prompt、evidence level 和任务顺序；
2. 使用固定随机种子生成 A/B 盲化展示；
3. 真实外部专家只读取自己的 assignment；
4. 记录 Evidence Correctness、Unsupported Claim Rate、Citation Usefulness、Missing-field Correctness、总体偏好和完成时间；
5. 按 `metadata_only/abstract_only/fulltext` 分层聚合；
6. 报告真实专家数、模拟数、完成率、分布、置信区间和 inter-rater agreement；
7. 真实专家数量或协议不足时保持 `awaiting_real_experts`。

LLM 评分、开发者自评或 `is_simulated=true` assignment 只能用于流程调试，不能升级 `expert_outcome_validation`。
