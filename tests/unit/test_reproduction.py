import pytest

from research_navigator.analysis.reproduction import (
    ReproductionDimension,
    assess_reproduction,
    calculate_reproduction_assessment,
)
from research_navigator.analysis.structured import PaperAnalysisOutput
from research_navigator.models import Paper


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/third-party/implementation",
        "https://github.com.attacker.invalid/code",
        "https://example.invalid/?next=github.com",
    ],
)
def test_repository_mention_is_not_verified_open_source(url: str) -> None:
    paper = Paper(
        id=1,
        title="Synthetic",
        normalized_title="synthetic",
        source_urls_json="[]",
        publisher_url=url,
    )
    analysis = PaperAnalysisOutput(
        paper_id=1,
        evidence_level="abstract_only",
        executive_summary="Synthetic",
        summary="Synthetic",
    )
    result = assess_reproduction(paper, analysis)
    code = next(item for item in result.dimensions if item.name == "code_availability")
    assert code.status == "unknown"
    assert code.score is None
    assert "许可" in code.evidence


def test_unknown_is_excluded_but_missing_is_known_negative() -> None:
    assessment = calculate_reproduction_assessment(
        [
            ReproductionDimension(
                name="code_availability",
                weight=0.2,
                status="unknown",
                score=None,
                evidence="Repository was not checked.",
            ),
            ReproductionDimension(
                name="data_availability",
                weight=0.2,
                status="missing",
                score=0.0,
                evidence="The paper explicitly states the data is private.",
            ),
            ReproductionDimension(
                name="method_completeness",
                weight=0.6,
                status="verified",
                score=0.8,
                evidence="Full method section is available.",
            ),
        ]
    )

    assert assessment.score == 60.0
    assert assessment.evidence_coverage == 0.8
    assert "data_availability" in assessment.blocking_reasons
    assert "code_availability" not in assessment.blocking_reasons


def test_all_unknown_reproduction_dimensions_are_not_zero() -> None:
    assessment = calculate_reproduction_assessment(
        [
            ReproductionDimension(
                name="code_availability", weight=0.5, status="unknown", score=None,
                evidence="尚未核验。",
            ),
            ReproductionDimension(
                name="data_availability", weight=0.5, status="unknown", score=None,
                evidence="尚未核验。",
            ),
        ]
    )
    assert assessment.score is None
    assert assessment.evidence_coverage is None


def test_abstract_only_readiness_keeps_dimensions_but_hides_insufficient_score() -> None:
    paper = Paper(id=1, title="A paper", abstract="We use Dataset X and a Transformer method.")
    analysis = PaperAnalysisOutput(
        paper_id=1,
        evidence_level="abstract_only",
        executive_summary="A summary",
        summary="A summary",
        methods=["Transformer"],
        datasets=["Dataset X"],
        metrics=["F1"],
    )
    result = assess_reproduction(paper, analysis)
    assert result.score is None
    assert result.evidence_coverage is not None and result.evidence_coverage > 0
    assert len(result.dimensions) >= 2
    assert result.score_version == "reproduction-v3"
    assert result.recommended_first_step


def test_metrics_without_protocol_are_unknown() -> None:
    analysis = PaperAnalysisOutput(
        paper_id=1,
        evidence_level="abstract_only",
        executive_summary="A summary",
        summary="A summary",
        metrics=["F1"],
    )
    result = assess_reproduction(Paper(id=1, title="A paper"), analysis)
    protocol = next(item for item in result.dimensions if item.name == "evaluation_protocol")
    assert protocol.status == "unknown"


def test_sufficient_known_reproduction_dimensions_show_score() -> None:
    dimensions = [
        ReproductionDimension(
            name="code", weight=0.3, status="verified", score=0.9, evidence="verified"
        ),
        ReproductionDimension(
            name="method", weight=0.3, status="partial", score=0.6, evidence="partial"
        ),
        ReproductionDimension(
            name="data", weight=0.4, status="unknown", score=None, evidence="unknown"
        ),
    ]
    result = calculate_reproduction_assessment(dimensions)
    assert result.score is not None
