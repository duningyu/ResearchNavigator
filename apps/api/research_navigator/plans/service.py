"""Generate editable research plans from confirmed candidate gaps."""

from __future__ import annotations


def default_plan_items(gap_claim: str) -> list[dict[str, object]]:
    return [
        {
            "category": "prerequisite_reading",
            "title": "阅读任务定义与评价协议综述",
            "description": "核对所选论文的研究问题、适用条件和评价对象；记录仍需补充的原文依据。",
            "sequence": 1,
            "purpose": "确认论文与当前研究问题是否可比较，避免任务错配。",
            "expected_output": "任务定义对照表，列出输入输出、适用条件和待核验引用。",
        },
        {
            "category": "core_reading",
            "title": "精读支持证据与反向证据",
            "description": f"围绕候选陈述逐篇记录支持、相邻和反向证据：{gap_claim}",
            "sequence": 2,
            "purpose": "界定候选陈述的支持范围，不把推断当作作者结论。",
            "expected_output": "逐篇证据核对记录，区分原文支持、反例和未知项。",
        },
        {
            "category": "reproduction",
            "title": "选择一个代码和数据可验证的基线",
            "description": "先复现公开基线，不以未核验仓库作为完成依据。",
            "sequence": 3,
            "purpose": "确认基线的代码、数据和运行条件是否可用。",
            "expected_output": "基线运行条件清单与复现日志；未运行项目明确标注。",
        },
        {
            "category": "dataset_preparation",
            "title": "核对材料与评价协议是否适用",
            "description": (
                "列出材料来源、授权范围、评价对象与独立验证方式；"
                "若涉及训练数据，另行记录切分边界和泄漏检查。"
            ),
            "sequence": 4,
            "purpose": "检查材料授权、评价可比性及可能的数据泄漏。",
            "expected_output": "数据来源与实验设置核对记录，包含授权及独立验证边界。",
        },
        {
            "category": "minimal_experiment",
            "title": "运行最小可行对比实验",
            "description": (
                "围绕已确认的问题选择可复现基线，只改变一个因素，记录对照结果和失败条件。"
            ),
            "sequence": 5,
            "purpose": "用最小对照检验候选假设，不以单次结果扩大结论。",
            "expected_output": "单因素对照结果表、运行配置、失败条件和待验证问题说明。",
        },
        {
            "category": "risk_check",
            "title": "执行候选空白反证和失败退出检查",
            "description": "若扩展检索找到高度直接的既有工作或基线无稳定增益，则收缩或退出该候选。",
            "sequence": 6,
            "purpose": "主动寻找能推翻候选的证据并记录退出条件。",
            "expected_output": "反证检查表与保留、收缩或退出候选的理由。",
        },
        {
            "category": "milestone",
            "title": "形成导师评审材料",
            "description": "输出检索式、证据矩阵、反向证据、复现结果和主张边界。",
            "sequence": 7,
            "purpose": "汇总可追溯材料供人工判断下一步，不自动确认科研结论。",
            "expected_output": "评审材料索引，连接研究问题、论文、证据及尚未解决的限制。",
        },
    ]
