"""Explainable research-direction matching with missing-aware normalization."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from pydantic import BaseModel

from research_navigator.analysis.structured import PaperAnalysisOutput
from research_navigator.models import Paper, ResearchProfile, ResearchProject


class WeightedScoreResult(BaseModel):
    score: float | None
    evidence_coverage: float | None
    components: dict[str, float | None]
    reasons: dict[str, str]
    score_version: str = "direction-match-v3"


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
    score = None if available_weight == 0 else weighted / available_weight
    coverage = (
        None if available_weight == 0 or total_weight == 0 else available_weight / total_weight
    )
    return WeightedScoreResult(
        score=None if score is None else round(max(0.0, min(1.0, score)) * 100, 2),
        evidence_coverage=None if coverage is None else round(coverage, 4),
        components=dict(components),
        reasons={},
    )


def _tokens(text: str) -> set[str]:
    tokens: set[str] = set(re.findall(r"[a-z0-9]+", text.lower()))
    for chunk in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(chunk) > 1:
            tokens.add(chunk)
            tokens.update(chunk[index : index + 2] for index in range(len(chunk) - 1))
    return {token for token in tokens if len(token) > 1}


def _overlap(left: str, right: str) -> float | None:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return None
    shared = a & b
    if not shared:
        return 0.0
    return len(shared) / len(a | b)


def _json_labels(raw: str) -> str:
    """Flatten paper metadata labels without treating malformed metadata as evidence."""
    try:
        values = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    if not isinstance(values, list):
        return ""
    labels: list[str] = []
    for value in values:
        if isinstance(value, str):
            labels.append(value)
        elif isinstance(value, dict):
            labels.extend(str(item) for item in value.values() if item is not None)
    return " ".join(labels)


def assess_direction_match(
    profile: ResearchProfile | None,
    paper: Paper,
    analysis: PaperAnalysisOutput,
    *,
    project: ResearchProject | None = None,
) -> WeightedScoreResult:
    if project is None and profile is None:
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
    keywords = json.loads(profile.keywords_json) if profile is not None else []
    context_text = " ".join(
        filter(
            None,
            [
                project.name if project is not None else "",
                project.broad_direction if project is not None else "",
                project.description if project is not None else "",
                profile.broad_direction if profile is not None else "",
                profile.major if profile is not None else "",
                " ".join(keywords),
            ],
        )
    )
    paper_text = " ".join(
        filter(
            None,
            [
                paper.title,
                paper.abstract or "",
                _json_labels(paper.keywords_json),
                _json_labels(paper.concepts_json),
                _json_labels(paper.fields_of_study_json),
                " ".join(analysis.methods),
                " ".join(analysis.core_methods),
                analysis.research_problem or "",
                analysis.task_definition.input or "",
                analysis.task_definition.output or "",
            ],
        )
    )
    task_text = " ".join(
        filter(
            None,
            [
                analysis.research_problem or "",
                analysis.task_definition.input or "",
                analysis.task_definition.output or "",
                analysis.task_definition.setting or "",
                " ".join(analysis.inputs),
                " ".join(analysis.outputs),
                paper.abstract or "",
            ],
        )
    )
    components = {
        "semantic_similarity": _overlap(context_text, paper_text),
        # Profile currently has no separately verified modality/output/protocol contracts.
        # Never fill these from a domain template or reward a declared hardware budget.
        "task_alignment": _overlap(
            " ".join(
                filter(
                    None,
                    [
                        project.broad_direction if project is not None else "",
                        project.description if project is not None else "",
                        profile.broad_direction if profile is not None else "",
                    ],
                )
            ),
            analysis.research_problem or task_text,
        ),
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
