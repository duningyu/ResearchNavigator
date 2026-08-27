"""Generate editable research plans from confirmed candidate gaps."""

from __future__ import annotations


def default_plan_items(gap_claim: str) -> list[dict[str, object]]:
    return [
        {
            "category": "prerequisite_reading",
            "title": "阅读任务定义与评价协议综述",
            "description": "明确异常检测、异常预测、未来窗口风险与固定预算排序的边界。",
            "sequence": 1,
        },
        {
            "category": "core_reading",
            "title": "精读支持证据与反向证据",
            "description": f"围绕候选陈述逐篇记录支持、相邻和反向证据：{gap_claim}",
            "sequence": 2,
        },
        {
            "category": "reproduction",
            "title": "选择一个代码和数据可验证的基线",
            "description": "先复现公开基线，不以未核验仓库作为完成依据。",
            "sequence": 3,
        },
        {
            "category": "dataset_preparation",
            "title": "建立因果切分和数据泄漏审计",
            "description": "训练预处理仅基于 train；validation 选择；frozen test 只做锁定后报告。",
            "sequence": 4,
        },
        {
            "category": "minimal_experiment",
            "title": "运行最小可行对比实验",
            "description": "比较点级检测后排序与历史窗口到未来 Horizon 的直接风险排序。",
            "sequence": 5,
        },
        {
            "category": "risk_check",
            "title": "执行候选空白反证和失败退出检查",
            "description": "若扩展检索找到高度直接的既有工作或基线无稳定增益，则收缩或退出该候选。",
            "sequence": 6,
        },
        {
            "category": "milestone",
            "title": "形成导师评审材料",
            "description": "输出检索式、证据矩阵、反向证据、复现结果和主张边界。",
            "sequence": 7,
        },
    ]
