from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from research_navigator.documents.ingest import ingest_public_pdf
from research_navigator.documents.open_evidence import OpenMaterialCandidate
from research_navigator.documents.remote_fetch import FetchedPDF
from research_navigator.documents.security import DocumentSecurityError


def candidate(**overrides: object) -> OpenMaterialCandidate:
    values = {
        "source": "arxiv",
        "source_record_id": "2401.12345v2",
        "pdf_url": "https://arxiv.org/pdf/2401.12345v2",
        "license": "cc-by",
        "rights_basis": "arxiv_license",
        "cache_policy": "shared_durable",
    }
    values.update(overrides)
    return OpenMaterialCandidate.model_validate(values)


def fetched() -> FetchedPDF:
    return FetchedPDF(
        data=b"%PDF-1.7", content_type=None,
        final_url="https://arxiv.org/pdf/2401.12345v2",
        sha256="a" * 64, response_hash="b" * 64,
    )


def test_public_ingest_reuses_existing_shared_document_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = SimpleNamespace(id=7)
    session = Mock()
    session.scalar.return_value = existing
    storage = Mock()
    result = ingest_public_pdf(
        session, settings=SimpleNamespace(max_pdf_bytes=100),
        paper=SimpleNamespace(id=3, doi=None, arxiv_id="2401.12345v2", external_ids_json="{}"),
        candidate=candidate(), fetched=fetched(), acquisition_run_id="run-1", storage=storage,
    )
    assert result.cache_hit is True
    assert result.document is existing
    storage.put.assert_not_called()
    session.add.assert_not_called()
    monkeypatch.setattr(
        "research_navigator.documents.ingest.parse_pdf",
        lambda _: pytest.fail("parsed on cache hit"),
    )


def test_public_ingest_rejects_wrong_arxiv_identity_before_insert() -> None:
    session = Mock()
    with pytest.raises(DocumentSecurityError, match="identity"):
        ingest_public_pdf(
            session, settings=SimpleNamespace(max_pdf_bytes=100),
            paper=SimpleNamespace(id=3, doi=None, arxiv_id="2401.12345v2", external_ids_json="{}"),
            candidate=candidate(source_record_id="2401.99999v1"),
            fetched=fetched(), acquisition_run_id="run-1", storage=Mock(),
        )
    session.add.assert_not_called()


def test_public_ingest_rejects_ambiguous_cache_policy() -> None:
    with pytest.raises(DocumentSecurityError, match="shared caching"):
        ingest_public_pdf(
            Mock(), settings=SimpleNamespace(max_pdf_bytes=100),
            paper=SimpleNamespace(id=3, doi=None, arxiv_id="2401.12345v2", external_ids_json="{}"),
            candidate=candidate(cache_policy="not_cacheable"),
            fetched=fetched(), acquisition_run_id="run-1", storage=Mock(),
        )
