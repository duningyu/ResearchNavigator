from research_navigator.analysis.matching import (
    assess_direction_match,
    missing_aware_weighted_score,
)
from research_navigator.analysis.structured import PaperAnalysisOutput
from research_navigator.models import Paper, ResearchProfile


def test_compute_constraint_alone_cannot_make_an_unrelated_paper_relevant() -> None:
    paper = Paper(id=1, title="Image semantic segmentation", abstract="Pixel classification")
    analysis = PaperAnalysisOutput(
        paper_id=1, evidence_level="abstract_only", summary="Pixels", executive_summary="Pixels"
    )
    profile = ResearchProfile(
        broad_direction="future window warning", keywords_json="[]", compute_constraints="one GPU"
    )
    result = assess_direction_match(profile, paper, analysis)
    assert result.components["resource_fit"] is None
    assert result.score == 0


def test_matching_has_no_industrial_template_for_a_segmentation_direction() -> None:
    paper = Paper(id=1, title="Semantic segmentation", abstract="We study semantic segmentation.")
    analysis = PaperAnalysisOutput(
        paper_id=1,
        evidence_level="abstract_only",
        summary="Pixels",
        executive_summary="Pixels",
        research_problem="semantic segmentation",
    )
    profile = ResearchProfile(broad_direction="semantic segmentation", keywords_json="[]")
    result = assess_direction_match(profile, paper, analysis)
    assert result.components["task_alignment"] == 1
    assert result.components["data_modality"] is None


def test_missing_aware_score_renormalizes_only_over_available_components() -> None:
    result = missing_aware_weighted_score(
        components={
            "semantic_similarity": 0.8,
            "task_alignment": 1.0,
            "data_modality": None,
        },
        weights={
            "semantic_similarity": 0.35,
            "task_alignment": 0.25,
            "data_modality": 0.15,
        },
    )

    expected = (0.8 * 0.35 + 1.0 * 0.25) / (0.35 + 0.25)
    assert result.score == round(expected * 100, 2)
    assert result.evidence_coverage == round((0.35 + 0.25) / (0.35 + 0.25 + 0.15), 4)
    assert result.components["data_modality"] is None
