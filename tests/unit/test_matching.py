from research_navigator.analysis.matching import missing_aware_weighted_score


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
