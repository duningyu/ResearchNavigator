from __future__ import annotations

import pytest

from research_navigator.analysis.llm_validation import validate_and_merge_llm_analysis
from research_navigator.analysis.providers import CitationValidationError
from research_navigator.analysis.structured import CitationLocator, analyze_accessible_text


def deterministic(level: str = "abstract_only"):
    citation = CitationLocator(source_type="abstract", section="Abstract", chunk_id=None)
    return analyze_accessible_text(
        paper_id=1,
        text="We study future alert ranking with a temporal convolutional network.",
        evidence_level=level,
        citations=[citation],
    )


def test_valid_llm_fields_are_additive_and_citation_bound() -> None:
    merged = validate_and_merge_llm_analysis(
        deterministic("abstract_only"),
        {
            "research_background": "Industrial alerts are highly imbalanced.",
            "method_innovation": ["A bounded ranking head."],
            "citations": [
                {"field": "research_background", "chunk_id": None},
                {"field": "method_innovation", "chunk_id": None},
            ],
        },
        accessible_snippets=[
            {
                "chunk_id": None,
                "text": "Industrial alerts are highly imbalanced. A bounded ranking head is used.",
                "citation": citation_payload(),
            }
        ],
        evidence_level="abstract_only",
    )
    assert merged.research_background == "Industrial alerts are highly imbalanced."
    assert merged.method_innovation == ["A bounded ranking head."]
    assert merged.field_states["method_innovation"] == "evidenced"
    assert merged.field_citations["method_innovation"][0].source_type == "abstract"


def citation_payload() -> dict[str, object]:
    return {
        "source_type": "abstract",
        "section": "Abstract",
        "page_start": None,
        "page_end": None,
        "chunk_id": None,
    }


def test_llm_field_without_local_citation_is_rejected() -> None:
    with pytest.raises(CitationValidationError, match="research_background"):
        validate_and_merge_llm_analysis(
            deterministic(),
            {"research_background": "Unsupported", "citations": []},
            accessible_snippets=[
                {"chunk_id": None, "text": "Evidence", "citation": citation_payload()}
            ],
            evidence_level="abstract_only",
        )


def test_llm_cross_chunk_citation_is_rejected() -> None:
    with pytest.raises(CitationValidationError, match="was not supplied"):
        validate_and_merge_llm_analysis(
            deterministic(),
            {
                "research_background": "Unsupported",
                "citations": [{"field": "research_background", "chunk_id": 999}],
            },
            accessible_snippets=[
                {
                    "chunk_id": 1,
                    "text": "Evidence",
                    "citation": citation_payload() | {"chunk_id": 1},
                }
            ],
            evidence_level="open_fulltext",
        )


def test_abstract_level_cannot_claim_fulltext_only_protocol() -> None:
    with pytest.raises(CitationValidationError, match="experimental_protocol"):
        validate_and_merge_llm_analysis(
            deterministic(),
            {
                "experimental_protocol": ["Random 80/20 split"],
                "citations": [{"field": "experimental_protocol", "chunk_id": None}],
            },
            accessible_snippets=[
                {"chunk_id": None, "text": "Random 80/20 split", "citation": citation_payload()}
            ],
            evidence_level="abstract_only",
        )
