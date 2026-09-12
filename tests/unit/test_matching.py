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
    assert result.score is None
    assert result.evidence_coverage is None


def test_missing_direction_profile_is_unknown_not_zero() -> None:
    paper = Paper(id=1, title="A paper", abstract="An abstract")
    analysis = PaperAnalysisOutput(
        paper_id=1, evidence_level="abstract_only", summary="Summary", executive_summary="Summary"
    )
    result = assess_direction_match(None, paper, analysis)
    assert result.score is None
    assert result.evidence_coverage is None


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


def test_negation_scope_does_not_hide_topic_in_without_labels_phrase() -> None:
    from research_navigator.gaps.eligibility import evaluate_evidence

    row = {
        "paper_id": 1,
        "work_identity": "paper-1",
        "research_problem": "We study anomaly detection without labels.",
        "limitations_author_stated": ["Evaluation is limited to one benchmark."],
        "field_states": {
            "research_problem": "evidenced",
            "limitations_author_stated": "evidenced",
        },
        "field_citations": {
            "research_problem": [{
                "source_type": "abstract", "section": "Abstract",
                "supporting_text": "We study anomaly detection without labels.",
                "material_verified": True,
            }],
            "limitations_author_stated": [{
                "source_type": "abstract", "section": "Abstract",
                "supporting_text": "Evaluation is limited to one benchmark.",
                "material_verified": True,
            }],
        },
    }

    decision = evaluate_evidence("anomaly detection", [row])

    assert decision.evidence[0].relation == "direct"
