"""Generate editable, plan-kind-aware research plans."""

# Long user-facing plan copy is intentionally kept as complete strings.
# ruff: noqa: E501

from __future__ import annotations

from typing import Literal

PlanKind = Literal["reading", "exploration", "confirmed_gap", "manual"]


def _item(
    category: str, title: str, description: str, sequence: int, purpose: str, expected_output: str
) -> dict[str, object]:
    return {
        "category": category,
        "title": title,
        "description": description,
        "sequence": sequence,
        "purpose": purpose,
        "expected_output": expected_output,
    }


def build_plan_items(
    *, plan_kind: PlanKind, objective: str, gap_claim: str | None = None
) -> list[dict[str, object]]:
    if plan_kind == "reading":
        specs = [
            (
                "reading_question",
                "明确本次阅读要回答的问题",
                "先明确为什么读，而不是机械阅读。",
                "把阅读目标与当前研究课题连接起来。",
                "1～3 个阅读问题。",
            ),
            (
                "reading_triage",
                "快速判断论文是否值得精读",
                "浏览标题、摘要、研究问题、核心方法与主要结论；区分已有证据和仍需正文核验的部分。",
                "用最小成本决定精读、略读或暂不继续。",
                "精读 / 略读 / 暂不继续的判断及理由。",
            ),
            (
                "core_reading",
                "精读研究问题与核心方法",
                "围绕论文真正解决的问题、输入输出、核心方法以及作者主张逐项记录。",
                "形成可复用的结构化方法理解。",
                "结构化方法笔记。",
            ),
            (
                "evidence_notes",
                "记录关键证据与结论边界",
                "把作者明确支持的内容、当前未知内容和自己推测的内容分开。",
                "避免把阅读推断误写成论文证据。",
                "证据笔记与待核验项。",
            ),
            (
                "direction_link",
                "判断与当前研究课题的关联",
                "记录这篇论文能为当前课题提供的方法、问题定义、对比对象或反例。",
                "明确论文对当前课题的实际帮助。",
                "值得借鉴 / 仅背景相关 / 暂无直接关系的阅读结论。",
            ),
            (
                "reading_output",
                "形成阅读结论与下一步阅读清单",
                "汇总本次阅读结果与仍需核验的内容。",
                "把阅读转化为后续可执行的研究动作。",
                "阅读总结 + 后续需要阅读或核验的论文/问题。",
            ),
        ]
    elif plan_kind == "exploration":
        specs = [
            (
                "exploration_question",
                "把当前想法改写成可验证问题",
                "不要直接写研究空白，而是写成能够被证据支持或推翻的问题。",
                "为探索设置可证伪边界。",
                "一个有边界的探索性研究问题。",
            ),
            (
                "support_search",
                "寻找支持该问题的已有证据",
                "从当前论文和扩展检索中记录支持该问题的研究与作者明确局限。",
                "建立支持性证据基线。",
                "支持性证据清单。",
            ),
            (
                "counter_search",
                "执行反向检索并尝试推翻当前判断",
                "主动搜索可能已经解决该问题的论文、相邻任务、不同术语和近义表达。",
                "优先寻找能推翻候选判断的证据。",
                "反向证据与检索式记录。",
            ),
            (
                "neighbor_comparison",
                "比较相邻工作，排除只是检索遗漏",
                "比较任务定义、方法、数据条件和评价目标；不要求所有论文都有完整数据集或协议字段。",
                "区分真实差异与检索遗漏。",
                "相邻工作差异矩阵。",
            ),
            (
                "minimal_validation",
                "设计一个低成本验证动作",
                "选择补读论文、检查公开代码、做小规模复现或补充检索中的一种最小动作。",
                "用低成本动作减少关键不确定性。",
                "一个可在短时间完成的验证任务。",
            ),
            (
                "decision_gate",
                "决定继续、收缩还是放弃",
                "根据支持证据、反向证据和验证结果，明确继续探索、收缩问题或放弃候选。",
                "让探索以可审计决策收束。",
                "决策及理由。",
            ),
        ]
    elif plan_kind == "manual":
        specs = [
            (
                "manual_action",
                "定义下一步行动",
                f"使用用户填写的 objective 作为当前行动背景：{objective}",
                "由用户自行定义行动范围，不自动推断研究阶段。",
                "填写本次行动的具体产出。",
            )
        ]
    else:
        return _confirmed_gap_items(gap_claim or objective)
    return [
        _item(category, title, description, index, purpose, output)
        for index, (category, title, description, purpose, output) in enumerate(specs, 1)
    ]


def _confirmed_gap_items(gap_claim: str) -> list[dict[str, object]]:
    specs = [
        (
            "prerequisite_reading",
            "阅读任务定义与评价协议综述",
            "核对研究问题、适用条件和评价对象；记录仍需补充的原文依据。",
            "确认论文与当前研究问题是否可比较，避免任务错配。",
            "任务定义对照表与待核验引用。",
        ),
        (
            "core_reading",
            "精读支持证据与反向证据",
            f"围绕候选陈述逐篇记录支持、相邻和反向证据：{gap_claim}",
            "界定候选陈述的支持范围，不把推断当作作者结论。",
            "逐篇证据核对记录。",
        ),
        (
            "reproduction",
            "选择一个代码和数据可验证的基线",
            "先复现公开基线，不以未核验仓库作为完成依据。",
            "确认代码、数据和运行条件是否可用。",
            "基线运行条件清单与复现日志。",
        ),
        (
            "dataset_preparation",
            "核对材料与评价协议是否适用",
            "列出材料来源、授权范围、评价对象与独立验证方式，并记录切分边界和泄漏检查。",
            "检查材料授权、评价可比性及数据泄漏。",
            "数据来源与实验设置核对记录。",
        ),
        (
            "minimal_experiment",
            "运行最小可行对比实验",
            "围绕已确认的问题选择可复现基线，只改变一个因素，记录对照结果和失败条件。",
            "用最小对照检验候选假设。",
            "单因素对照结果表与运行配置。",
        ),
        (
            "risk_check",
            "执行候选空白反证和失败退出检查",
            "若扩展检索找到高度直接的既有工作或基线无稳定增益，则收缩或退出候选。",
            "主动寻找能推翻候选的证据。",
            "反证检查表与退出理由。",
        ),
        (
            "milestone",
            "形成导师评审材料",
            "输出检索式、证据矩阵、反向证据、复现结果和主张边界。",
            "汇总可追溯材料供人工判断。",
            "评审材料索引。",
        ),
    ]
    return [
        _item(category, title, description, index, purpose, output)
        for index, (category, title, description, purpose, output) in enumerate(specs, 1)
    ]


def default_plan_items(gap_claim: str) -> list[dict[str, object]]:
    """Backward-compatible name for the rigorous confirmed-gap template."""
    return build_plan_items(plan_kind="confirmed_gap", objective=gap_claim, gap_claim=gap_claim)
