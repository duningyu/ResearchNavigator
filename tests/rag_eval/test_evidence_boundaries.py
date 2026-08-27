from research_navigator.analysis.structured import analyze_accessible_text


def test_abstract_only_analysis_does_not_invent_fulltext_future_work() -> None:
    text = (
        "We propose a Transformer for multivariate time-series anomaly detection. "
        "Future work will evaluate the method on additional industrial datasets."
    )

    analysis = analyze_accessible_text(
        paper_id=1,
        text=text,
        evidence_level="abstract_only",
        citations=[
            {
                "source_type": "abstract",
                "section": "Abstract",
                "page_start": None,
                "page_end": None,
                "chunk_id": None,
            }
        ],
    )

    assert analysis.methods == ["Transformer"]
    assert analysis.future_work_explicit == []
    assert analysis.limitations_author_stated == []
    assert "future_work_explicit" in analysis.missing_fields
    assert any("摘要级" in warning for warning in analysis.warnings)


def test_fulltext_analysis_can_extract_explicit_future_work_with_citation() -> None:
    analysis = analyze_accessible_text(
        paper_id=2,
        text=(
            "Method. We use a temporal convolutional network for risk ranking. "
            "Future work will study cross-device generalization."
        ),
        evidence_level="user_uploaded_fulltext",
        citations=[
            {
                "source_type": "user_upload",
                "section": "Conclusion",
                "page_start": 8,
                "page_end": 8,
                "chunk_id": 12,
            }
        ],
    )

    assert "Temporal Convolutional Network" in analysis.methods
    assert analysis.future_work_explicit
    assert analysis.citations[0].chunk_id == 12


def test_empty_task_definition_is_unknown_not_evidenced() -> None:
    analysis = analyze_accessible_text(
        paper_id=3,
        text="A benchmark summary reports evaluation results.",
        evidence_level="abstract_only",
        citations=[
            {
                "source_type": "abstract",
                "section": "Abstract",
                "page_start": None,
                "page_end": None,
                "chunk_id": None,
            }
        ],
    )

    assert analysis.task_definition.input is None
    assert analysis.task_definition.output is None
    assert analysis.task_definition.setting is None
    assert analysis.field_states["task_definition"] == "unknown"
    assert analysis.field_citations["task_definition"] == []


def test_field_citations_align_each_claim_to_its_supporting_sentence_and_chunk() -> None:
    method_sentence = "We propose a Transformer model for multivariate anomaly detection."
    future_sentence = "Future work will evaluate cross-device generalization."
    analysis = analyze_accessible_text(
        paper_id=4,
        text=f"{method_sentence} {future_sentence}",
        evidence_level="user_uploaded_fulltext",
        citations=[],
        evidence_spans=[
            {
                "text": method_sentence,
                "citation": {
                    "source_type": "user_upload",
                    "section": "Method",
                    "page_start": 2,
                    "page_end": 2,
                    "chunk_id": 21,
                },
            },
            {
                "text": future_sentence,
                "citation": {
                    "source_type": "user_upload",
                    "section": "Conclusion",
                    "page_start": 8,
                    "page_end": 8,
                    "chunk_id": 22,
                },
            },
        ],
    )

    method_citations = analysis.field_citations["method_innovation"]
    future_citations = analysis.field_citations["future_work_explicit"]
    assert [citation.chunk_id for citation in method_citations] == [21]
    assert [citation.chunk_id for citation in future_citations] == [22]
    assert method_citations[0].supporting_text == method_sentence
    assert future_citations[0].supporting_text == future_sentence
    assert analysis.citation_granularity == "sentence_to_chunk"
