# 候选研究空白方法

## 1. 定义

系统输出的是**候选研究空白**：在明确数据源、查询式、时间和语料范围内，某个任务/数据/方法/协议组合的直接证据较少。它不是“从未有人研究”的证明。

每条候选固定 `not_novelty_proof=true`。

## 2. 证据矩阵

当前矩阵字段包括：论文、年份、任务、输入/输出、数据类型、数据集、监督、Horizon、方法、业务约束、类别不平衡、误报、事件级指标、代码/数据核验、Future Work、Limitations 和 evidence level。

缺失值保留为空，不用 LLM 猜测。

## 3. 候选生成

透明规则检查方向与语料是否覆盖：

- 未来窗口/预测目标；
- 风险排序或固定告警预算；
- 误报和事件级评价；
- 跨设备泛化；
- 代码/数据和复现证据。

规则输出 gap type、claim、scope、支持/相邻论文、覆盖度、风险、最小验证和建议问题。该规则是产品辅助逻辑，不应包装为新基础算法。

## 4. Challenge Queries

至少覆盖：

- 原始中英文/引号查询；
- early warning；
- failure prediction；
- predictive maintenance；
- fixed alarm budget / Top-K；
- event-level / false alarms；
- cross-device generalization；
- anomaly forecasting / future window risk；
- 方法名、旧术语、引用链和被引链（后两类当前 API 待补足）。

## 5. 反向证据

challenge 返回的是 `potential_counter_or_adjacent_evidence`，不是自动判定反证。用户需检查任务定义、输入输出、数据、Horizon 和评价协议是否真正重合。

## 6. 置信度

当前实现只提供保守 low/medium 状态，不给伪精确概率。高置信至少需要：

- 多个独立数据源正常；
- 中英文和同义词扩展；
- 引用/被引链；
- 纳入排除记录；
- 足够论文数和时间覆盖；
- 专家复核。

本版本不输出 high。

## 7. 最小验证实验

候选进入研究计划后，需要：baseline、baseline+候选、关键消融、参数敏感性、多随机种子、分组结果、运行成本、失败案例和退出条件。时序异常预警必须遵守 train/validation/frozen-test，不能 test-aware selection。

## 8. 失败退出条件

- challenge 找到高度直接、任务完全一致且已充分验证的既有工作；
- 所谓空白仅是术语不同；
- 数据集无法支撑目标输入输出；
- 最小实验相对基线无稳定收益；
- 复现阻断项无法在研究周期内解决；
- 改进只是减少报警数量并显著损失 Recall/Event Coverage。
