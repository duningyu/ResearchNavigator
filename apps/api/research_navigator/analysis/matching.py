"""Explainable research-direction matching with missing-aware normalization."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from pydantic import BaseModel

from research_navigator.analysis.structured import PaperAnalysisOutput
from research_navigator.models import Paper, ResearchProfile


class WeightedScoreResult(BaseModel):
    score: float
    evidence_coverage: float
    components: dict[str, float | None]
    reasons: dict[str, str]
    score_version: str = "direction-match-v2"


def missing_aware_weighted_score(
    *, components: Mapping[str, float | None], weights: Mapping[str, float]
) -> WeightedScoreResult:
    total_weight = sum(weights.values())
    available_weight = sum(weights[name] for name, value in components.items() if value is not None)
    weighted = sum(
        weights[name] * float(value)
        for name, value in components.items()
        if value is not None and name in weights
    )
    score = 0.0 if available_weight == 0 else weighted / available_weight
    coverage = 0.0 if total_weight == 0 else available_weight / total_weight
    return WeightedScoreResult(
        score=round(max(0.0, min(1.0, score)) * 100, 2),
        evidence_coverage=round(coverage, 4),
        components=dict(components),
        reasons={},
    )


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", text.lower())
        if len(token) > 1
    }


def _overlap(left: str, right: str) -> float | None:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return None
    return len(a & b) / max(1, len(a | b))


def assess_direction_match(
    profile: ResearchProfile | None, paper: Paper, analysis: PaperAnalysisOutput
) -> WeightedScoreResult:
    if profile is None:
        return missing_aware_weighted_score(
            components={
                "semantic_similarity": None,
                "task_alignment": None,
                "data_modality": None,
                "prediction_output": None,
                "evaluation_protocol": None,
                "resource_fit": None,
            },
            weights={
                "semantic_similarity": 0.35,
                "task_alignment": 0.25,
                "data_modality": 0.15,
                "prediction_output": 0.10,
                "evaluation_protocol": 0.10,
                "resource_fit": 0.05,
            },
        )
    keywords = json.loads(profile.keywords_json)
    profile_text = " ".join(
        filter(None, [profile.broad_direction or "", profile.major or "", " ".join(keywords)])
    )
    paper_text = " ".join(
        filter(
            None,
            [
                paper.title,
                paper.abstract or "",
                " ".join(analysis.methods),
                analysis.research_problem or "",
            ],
        )
    )
    components = {
        "semantic_similarity": _overlap(profile_text, paper_text),
        # Profile currently has no separately verified modality/output/protocol contracts.
        # Never fill these from a domain template or reward a declared hardware budget.
        "task_alignment": _overlap(profile.broad_direction or "", analysis.research_problem or ""),
        "data_modality": None,
        "prediction_output": None,
        "evaluation_protocol": None,
        "resource_fit": None,
    }
    result = missing_aware_weighted_score(
        components=components,
        weights={
            "semantic_similarity": 0.35,
            "task_alignment": 0.25,
            "data_modality": 0.15,
            "prediction_output": 0.10,
            "evaluation_protocol": 0.10,
            "resource_fit": 0.05,
        },
    )
    result.reasons = {
        name: (
            "缺少可核验条件，不计分"
            if value is None
            else "基于词语重合，仅作阅读线索，不证明任务相关"
        )
        for name, value in components.items()
    }
    return result
