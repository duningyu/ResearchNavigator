"""Bounded candidate-gap statements, explanations, and challenge-query generation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GapCandidateDraft(BaseModel):
    gap_type: str
    claim: str
    scope: str
    status: str = "generated"
    supporting_evidence: list[int] = Field(default_factory=list)
    adjacent_work: list[int] = Field(default_factory=list)
    counter_evidence: list[dict[str, object]] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    coverage: dict[str, object] = Field(default_factory=dict)
    confidence: str = "low"
    risk_factors: list[str] = Field(default_factory=list)
    minimal_validation: list[str] = Field(default_factory=list)
    suggested_research_question: str
    not_novelty_proof: bool = True


class GapExplanationPayload(BaseModel):
    version: int
    provider: str = "deterministic"
    direct_evidence: list[dict[str, Any]] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)
    supporting_papers: list[int] = Field(default_factory=list)
    weakening_papers: list[int] = Field(default_factory=list)
    absent_evidence: list[str] = Field(default_factory=list)
    direction_relation: dict[str, Any] = Field(default_factory=dict)
    novelty_risk_factors: list[str] = Field(default_factory=list)
    challenge_queries: list[str] = Field(default_factory=list)
    minimum_validation: list[str] = Field(default_factory=list)
    confidence_rationale: str
    not_novelty_proof: bool = True
    evidence_hash: str = ""


def make_gap_candidate(
    *, project_direction: str, paper_ids: list[int], evidence_matrix: list[dict[str, object]]
) -> GapCandidateDraft:
    has_future = any(row.get("prediction_horizon") for row in evidence_matrix)
    has_ranking = any(row.get("task") == "risk ranking" for row in evidence_matrix)
    if not has_future or not has_ranking:
        missing = "未来窗口预测" if not has_future else "固定预算风险排序"
        claim = (
            f"在本次检索范围（用户显式选择的论文集合）内，'{project_direction}' 相关语料对 "
            f"{missing} 的直接联合证据较少；"
            "该结论仅构成需要扩展检索与专家确认的候选研究空白。"
        )
        gap_type = "task_definition_and_evaluation_gap"
    else:
        claim = (
            f"在本次检索范围（用户显式选择的论文集合）内，'{project_direction}' 的跨设备、"
            f"误报约束与"
            "事件级评价联合证据仍不充分；该结论仅构成候选研究空白。"
        )
        gap_type = "robustness_and_protocol_gap"
    return GapCandidateDraft(
        gap_type=gap_type,
        claim=claim,
        scope=project_direction,
        supporting_evidence=paper_ids,
        adjacent_work=paper_ids,
        coverage={
            "selected_paper_count": len(evidence_matrix),
            "future_horizon_coverage": sum(
                bool(row.get("prediction_horizon")) for row in evidence_matrix
            ),
            "risk_ranking_coverage": sum(
                row.get("task") == "risk ranking" for row in evidence_matrix
            ),
            "fulltext_evidence_count": sum(
                row.get("evidence_level")
                in {"open_fulltext", "user_uploaded_fulltext", "publisher_authorized_fulltext"}
                for row in evidence_matrix
            ),
        },
        confidence="low",
        risk_factors=[
            "当前结论只覆盖用户显式选择的论文集合",
            "术语差异可能造成检索漏召回",
            "未完成充分的引用链、被引链和近邻方向扩展时不能证明新颖性",
            "摘要级论文不能支持正文实验协议、作者局限或 Future Work 的完整比较",
            "本结果不是创新性证明",
        ],
        minimal_validation=[
            "扩展同义词、邻近任务和跨数据库检索",
            "检查引用链、被引链和近期综述",
            "优先补齐候选关键论文全文证据",
            "由导师或领域专家复核候选空白",
            "在 validation-only 协议下设计最小基线实验",
        ],
        suggested_research_question=(
            f"如何在 {project_direction} 中同时控制误报、保持事件覆盖率，"
            "并对跨设备外推进行严格验证？"
        ),
        not_novelty_proof=True,
    )


def build_gap_explanation(
    *,
    version: int,
    claim: str,
    evidence_matrix: list[dict[str, Any]],
    supporting_evidence: list[int],
    counter_evidence: list[dict[str, Any]],
    direction_snapshot: dict[str, Any],
    risk_factors: list[str],
    challenge_queries: list[str],
    minimal_validation: list[str],
    confidence: str,
) -> GapExplanationPayload:
    direct = [
        {
            "paper_id": row.get("paper_id"),
            "title": row.get("title"),
            "task": row.get("task"),
            "prediction_horizon": row.get("prediction_horizon"),
            "methods": row.get("methods", []),
            "datasets": row.get("datasets", []),
            "metrics": row.get("metrics", []),
            "evidence_level": row.get("evidence_level", "metadata_only"),
            "missing_fields": row.get("missing_fields", []),
        }
        for row in evidence_matrix
    ]
    missing_counts: dict[str, int] = {}
    for row in evidence_matrix:
        for field in row.get("missing_fields", []) or []:
            missing_counts[str(field)] = missing_counts.get(str(field), 0) + 1
    absent = [
        f"{field}: {count}/{len(evidence_matrix)} 篇当前证据缺失"
        for field, count in sorted(missing_counts.items())
    ]
    if not absent:
        absent.append("仍需验证语料覆盖范围、同义词召回和未纳入论文是否会推翻候选空白。")
    weakening = [
        int(item["paper_id"]) for item in counter_evidence if isinstance(item.get("paper_id"), int)
    ]
    direction = direction_snapshot.get("project", {}).get(
        "broad_direction"
    ) or direction_snapshot.get("project", {}).get("name")
    inferences = [
        "候选空白来自所选论文证据矩阵中的未覆盖/弱覆盖维度，不等同于领域不存在相关研究。",
        f"候选空白与当前方向“{direction or '未设置'}”存在任务或评价协议层面的待验证关联。",
        "任何反例论文、全文新增证据或更广检索都可能降低该候选空白的可信度。",
    ]
    rationale = (
        f"当前置信度为 {confidence}：直接证据来自 {len(evidence_matrix)} 篇显式选择论文；"
        f"Challenge Search 返回 {len(weakening)} 篇潜在反例/邻近论文。"
    )
    return GapExplanationPayload(
        version=version,
        direct_evidence=direct,
        inferences=inferences,
        supporting_papers=supporting_evidence,
        weakening_papers=list(dict.fromkeys(weakening)),
        absent_evidence=absent,
        direction_relation={
            "direction_snapshot": direction_snapshot,
            "candidate_claim": claim,
            "relationship": "hypothesis_requiring_challenge_and_human_review",
        },
        novelty_risk_factors=risk_factors,
        challenge_queries=challenge_queries,
        minimum_validation=minimal_validation,
        confidence_rationale=rationale,
        not_novelty_proof=True,
    )


def generate_challenge_queries(scope: str) -> list[str]:
    base = scope.strip()
    queries = [
        f'"{base}"',
        f'"{base}" early warning',
        f'"{base}" failure prediction',
        f'"{base}" predictive maintenance',
        f'"{base}" fixed alarm budget top-k',
        f'"{base}" event-level evaluation false alarms',
        f'"{base}" cross-device generalization',
        "multivariate time series anomaly forecasting future window risk",
        "industrial early warning alert prioritization failure prediction",
    ]
    return list(dict.fromkeys(queries))
