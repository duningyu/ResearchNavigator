"""Regression witnesses for RN-UX-R1: absence is not a research gap."""

import pytest

from research_navigator.gaps.candidate import generate_challenge_queries, make_gap_candidate
from research_navigator.plans.service import default_plan_items


def test_explanation_direct_evidence_is_verified_original_text_not_inferred_metadata() -> None:
    from research_navigator.gaps.candidate import build_gap_explanation

    result = build_gap_explanation(
        version=1,
        claim="待核实",
        supporting_evidence=[1],
        counter_evidence=[],
        direction_snapshot={"project": {"broad_direction": "semantic segmentation"}},
        risk_factors=[],
        challenge_queries=[],
        minimal_validation=[],
        confidence="low",
        evidence_matrix=[
            {
                "paper_id": 1,
                "title": "Original title",
                "task": "heuristic task",
                "field_citations": {
                    "major_results": [
                        {
                            "source_type": "abstract",
                            "section": "abstract",
                            "supporting_text": "Actual quoted result.",
                            "material_verified": True,
                        },
                        {
                            "source_type": "abstract",
                            "supporting_text": "Unverified assertion",
                            "material_verified": False,
                        },
                    ]
                },
                "missing_fields": ["prediction_horizon"],
            },
            {"paper_id": 2, "title": "Reference only", "field_citations": {}},
        ],
    )
    assert result.direct_evidence == [
        {
            "paper_id": 1,
            "title": "Original title",
            "supporting_text": "Actual quoted result.",
            "source_type": "abstract",
            "section": "abstract",
        }
    ]
    assert "prediction_horizon" not in " ".join(result.absent_evidence)
    assert "low" not in result.confidence_rationale


@pytest.mark.parametrize(
    "direction", ["图像语义分割", "retrieval augmented generation", "未来窗口预警"]
)
def test_empty_material_cannot_generate_candidate(direction: str) -> None:
    with pytest.raises(ValueError, match="证据"):
        make_gap_candidate(project_direction=direction, paper_ids=[], evidence_matrix=[])


def test_unrelated_and_uncited_papers_cannot_generate_candidate() -> None:
    with pytest.raises(ValueError, match="证据|相关"):
        make_gap_candidate(
            project_direction="图像语义分割",
            paper_ids=[41, 83],
            evidence_matrix=[
                {"paper_id": 41, "research_problem": "anomaly detection", "task": "unknown"},
                {"paper_id": 83, "research_problem": None, "task": "unknown"},
            ],
        )


@pytest.mark.parametrize("direction", ["图像语义分割", "retrieval augmented generation"])
def test_challenge_does_not_append_foreign_domain(direction: str) -> None:
    queries = " ".join(generate_challenge_queries(direction)).lower()
    for foreign in ("industrial", "early warning", "failure prediction", "time series", "alarm"):
        assert foreign not in queries


def test_plan_does_not_invent_industrial_experiment() -> None:
    items = default_plan_items("核实图像语义分割的标注成本")
    text = " ".join(str(item) for item in items)
    for foreign in (
        "异常预测",
        "未来 Horizon",
        "固定预算排序",
        "点级检测",
        "因果切分",
        "frozen test",
    ):
        assert foreign not in text
