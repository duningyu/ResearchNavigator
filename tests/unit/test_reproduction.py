from research_navigator.analysis.reproduction import (
    ReproductionDimension,
    calculate_reproduction_assessment,
)


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
