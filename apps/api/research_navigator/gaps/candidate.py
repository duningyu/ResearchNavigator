"""Bounded candidate-gap statements, explanations, and challenge-query generation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from research_navigator.gaps.eligibility import EvidenceGateBlocked, evaluate_evidence


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
    selected = [row for row in evidence_matrix if row.get("paper_id") in paper_ids]
    gate = evaluate_evidence(project_direction, selected)
    if not gate.allowed:
        raise EvidenceGateBlocked(gate)
    citations = [
        c
        for e in gate.evidence
        if e.paper_id in gate.participating_ids
        for c in (
            e.author_future_work_citations
            if gate.candidate_kind == "author_suggestion"
            else e.claim_citations
        )
    ]
    quoted = "；".join(dict.fromkeys(str(c["supporting_text"]) for c in citations))
    claim = (
        f"在本次检索范围内，围绕“{project_direction}”可继续核实以下原文陈述的适用边界：{quoted}。"
        "这是作者建议或所选论文之间的待核实问题，不说明领域缺少相关研究。"
    )
    gap_type = gate.candidate_kind
    return GapCandidateDraft(
        gap_type=gap_type,
        claim=claim,
        scope=project_direction,
        supporting_evidence=gate.participating_ids,
        adjacent_work=gate.reference_only_ids,
        coverage={
            "eligibility": gate.model_dump(mode="json"),
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
            "摘要仅支持摘要中明确陈述且可定位的内容，不能推断未读取正文的结论",
            "本结果不是创新性证明",
        ],
        minimal_validation=[
            "扩展同义词、邻近任务和跨数据库检索",
            "检查引用链、被引链和近期综述",
            "优先补齐候选关键论文全文证据",
            "由导师或领域专家复核候选空白",
            "仅用验证集选择实验方案，锁定后再做独立测试",
        ],
        suggested_research_question=(
            f"在 {project_direction} 中，如何核实上述原文陈述的适用条件与已有工作的覆盖范围？"
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
            **{
                key: citation[key]
                for key in (
                    "supporting_text",
                    "source_type",
                    "section",
                    "chunk_id",
                    "page_start",
                    "page_end",
                )
                if citation.get(key) is not None
            },
        }
        for row in evidence_matrix
        if row.get("paper_id") in supporting_evidence
        for field in (
            "research_problem",
            "major_results",
            "limitations_author_stated",
            "future_work_explicit",
        )
        for citation in row.get("field_citations", {}).get(field, [])
        if citation.get("material_verified") is True and citation.get("supporting_text")
    ]
    missing_counts: dict[str, int] = {}
    for row in evidence_matrix:
        for field in row.get("missing_fields", []) or []:
            missing_counts[str(field)] = missing_counts.get(str(field), 0) + 1
    labels = {
        "prediction_horizon": "预测窗口",
        "research_problem": "研究问题",
        "major_results": "主要结果",
        "limitations_author_stated": "作者明确说明的局限",
        "future_work_explicit": "作者后续研究建议",
        "methods": "方法",
        "datasets": "数据集",
        "metrics": "评价指标",
        "split_protocol": "数据划分协议",
    }
    absent = list(
        dict.fromkeys(
            f"{labels.get(field, '待核实材料')}: {count}/{len(evidence_matrix)} 篇当前证据缺失"
            for field, count in sorted(missing_counts.items())
        )
    )
    if not absent:
        absent.append("仍需验证语料覆盖范围、同义词召回和未纳入论文是否会推翻候选空白。")
    weakening = [
        int(item["paper_id"])
        for item in counter_evidence
        if isinstance(item.get("paper_id"), int) and item.get("relationship") == "refutes"
    ]
    direction = direction_snapshot.get("project", {}).get(
        "broad_direction"
    ) or direction_snapshot.get("project", {}).get("name")
    inferences = [
        "候选问题只来自可定位原文陈述；缺失字段不等于研究缺陷或领域空白。",
        f"候选空白与当前方向“{direction or '未设置'}”存在任务或评价协议层面的待验证关联。",
        "任何反例论文、全文新增证据或更广检索都可能降低该候选空白的可信度。",
    ]
    rationale = (
        f"当前可信程度为{'待核实' if confidence == 'low' else '仍需复核'}："
        f"可定位证据来自 {len({item['paper_id'] for item in direct})} 篇参与论文；"
        f"已核验反驳关系 {len(weakening)} 篇。检索条目数量不提高置信度，待评估条目不是反例。"
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
        f'"{base}" survey',
        f'"{base}" replication',
        f'"{base}" limitations',
        f'"{base}" comparative evaluation',
    ]
    # A task synonym is permitted only when that task occurs in the input.
    if any(term in base.casefold() for term in ("预警", "异常风险", "early warning")):
        queries.extend([f'"{base}" early warning', f'"{base}" failure prediction'])
    return list(dict.fromkeys(queries))
