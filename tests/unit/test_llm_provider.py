import pytest

from research_navigator.analysis.providers import (
    CitationValidationError,
    DeterministicMockProvider,
    EvidenceBoundLLMProvider,
)


def test_provider_rejects_field_without_supported_citation() -> None:
    provider = EvidenceBoundLLMProvider(
        DeterministicMockProvider(
            {
                "summary": "Supported claim",
                "methods": ["Unsupported claim"],
                "citations": [{"field": "summary", "chunk_id": 1}],
            }
        )
    )

    with pytest.raises(CitationValidationError, match="methods"):
        provider.extract(
            paper_id=7,
            evidence_level="abstract_only",
            snippets=[{"chunk_id": 1, "text": "Supported claim"}],
        )


def test_provider_abstains_and_preserves_evidence_level() -> None:
    provider = EvidenceBoundLLMProvider(
        DeterministicMockProvider(
            {
                "summary": "Supported claim",
                "citations": [{"field": "summary", "chunk_id": 1}],
            }
        )
    )

    output = provider.extract(
        paper_id=7,
        evidence_level="abstract_only",
        snippets=[{"chunk_id": 1, "text": "Supported claim"}],
    )

    assert output["paper_id"] == 7
    assert output["evidence_level"] == "abstract_only"
    assert output["methods"] == []
    assert "methods" in output["missing_fields"]
    assert "未在当前可访问文本中找到。" in output["abstentions"]
