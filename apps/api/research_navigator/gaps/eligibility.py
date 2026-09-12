"""Conservative, citation-backed eligibility; missing information is never a gap.

This is an explainable lexical baseline, not a semantic relevance model. A
direction that cannot be aligned to cited task text abstains. Bibliographic
titles and retrieval scores alone cannot authorize a research claim.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

VERSION = "rn-ux-r1-evidence-v1"


class PaperEligibilityEvidence(BaseModel):
    paper_id: int
    work_identity: str
    relation: Literal["direct", "adjacent", "unrelated", "unknown"] = "unknown"
    relation_citations: list[dict[str, Any]] = Field(default_factory=list)
    claim_citations: list[dict[str, Any]] = Field(default_factory=list)
    author_future_work_citations: list[dict[str, Any]] = Field(default_factory=list)
    evidence_fingerprint: str


class GateDecision(BaseModel):
    allowed: bool
    reason_codes: list[str]
    reason: str
    actions: list[str]
    participating_ids: list[int]
    reference_only_ids: list[int]
    evidence_fingerprint: str
    evidence: list[PaperEligibilityEvidence]
    candidate_kind: str = "cross_paper"
    version: str = VERSION


class EvidenceGateBlocked(ValueError):
    def __init__(self, decision: GateDecision):
        self.decision = decision
        super().__init__(decision.reason)


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()


def _normalize(text: str) -> str:
    # Explicit language aliases, never universal domain expansion.
    for source, target in (
        ("图像语义分割", "semantic segmentation"),
        ("语义分割", "semantic segmentation"),
        ("检索增强生成", "retrieval augmented generation"),
        ("异常检测", "anomaly detection"),
        ("异常预测", "anomaly prediction"),
        ("风险排序", "risk ranking"),
        ("未来窗口", "future window"),
        ("时间序列", "time series"),
    ):
        text = text.replace(source, target)
    return " ".join(re.findall(r"\w+", text.casefold()))


def _citations(row: dict[str, Any], field: str) -> list[dict[str, Any]]:
    values = row.get(field)
    if not values or row.get("field_states", {}).get(field) != "evidenced":
        return []
    claims = values if isinstance(values, list) else [values]
    return [
        c
        for c in row.get("field_citations", {}).get(field, [])
        if isinstance(c, dict)
        and c.get("source_type")
        and c.get("material_verified") is True
        and (c.get("section") or c.get("chunk_id") or c.get("page_start"))
        and c.get("supporting_text")
        and any(
            _normalize(str(claim)) in _normalize(str(c["supporting_text"]))
            for claim in claims
            if _normalize(str(claim))
        )
    ]


def _has_scoped_topic_negation(text: str) -> bool:
    """Reject explicit topic dismissal, not a negated method condition."""
    return bool(
        re.search(
            r"\b(?:do|does|did)\s+not\s+(?:study|address|examine|focus\s+on|consider)\b"
            r"|\bnot\s+(?:related|relevant)\s+to\b"
            r"|\b(?:unrelated|irrelevant)\s+to\b"
            r"|\b(?:exclude|excluding)\s+(?:the\s+)?topic\b"
            r"|不研究|不涉及|无关|并非研究|未研究",
            text,
        )
    )


def evaluate_evidence(direction: str, rows: list[dict[str, Any]]) -> GateDecision:
    evidence: list[PaperEligibilityEvidence] = []
    normalized = _normalize(direction)
    stopwords = {"a", "an", "the", "of", "for", "and", "in", "with", "research", "study"}
    terms = set(normalized.split()) - stopwords
    for row in rows:
        relation_citations = _citations(row, "research_problem")
        cited_task = _normalize(" ".join(str(c["supporting_text"]) for c in relation_citations))
        overlap = terms & set(cited_task.split())
        # Scope the denial to the topic itself. For example, "without labels"
        # negates a method condition, not the subject "anomaly detection".
        denied = _has_scoped_topic_negation(cited_task)
        # At least two meaningful terms and most of the specified direction.
        aligned = (
            not denied
            and bool(terms)
            and (
                normalized in cited_task or (len(overlap) >= 2 and len(overlap) / len(terms) >= 0.6)
            )
        )
        claims = _citations(row, "limitations_author_stated") + _citations(row, "major_results")
        evidence.append(
            PaperEligibilityEvidence(
                paper_id=int(row["paper_id"]),
                work_identity=str(row.get("work_identity") or row.get("title") or row["paper_id"]),
                relation="direct" if aligned else "unknown",
                relation_citations=relation_citations,
                claim_citations=claims,
                author_future_work_citations=_citations(row, "future_work_explicit"),
                evidence_fingerprint=fingerprint(row),
            )
        )
    eligible = [e for e in evidence if e.relation == "direct" and e.claim_citations]
    distinct = {e.work_identity for e in eligible}
    authors = [e for e in evidence if e.relation == "direct" and e.author_future_work_citations]
    cross = len(distinct) >= 2
    participants = eligible if cross else authors[:1]
    allowed = bool(participants)
    return GateDecision(
        allowed=allowed,
        reason_codes=[] if allowed else ["INSUFFICIENT_RELEVANT_CITED_EVIDENCE"],
        reason="材料支持提出待核实问题，不构成领域空白证明。"
        if allowed
        else "相关性或关键证据尚不足，已停止生成候选研究空白。",
        actions=[]
        if allowed
        else ["补充与方向直接相关的论文及可定位的原文证据", "核对研究问题、作者局限或后续研究建议"],
        participating_ids=[e.paper_id for e in participants],
        reference_only_ids=[e.paper_id for e in evidence if e not in participants],
        evidence_fingerprint=fingerprint(
            {"version": VERSION, "direction": direction, "rows": rows}
        ),
        evidence=evidence,
        candidate_kind="cross_paper" if cross else "author_suggestion",
    )
