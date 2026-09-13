"""Shared ingestion for rights-approved public paper material."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.config import Settings
from research_navigator.data_plane.storage import DurableStorage, LocalStorage
from research_navigator.documents.index import index_document
from research_navigator.documents.material_binding import bind_material, expected_arxiv_identity
from research_navigator.documents.open_evidence import OpenMaterialCandidate
from research_navigator.documents.parser import parse_pdf
from research_navigator.documents.remote_fetch import FetchedPDF
from research_navigator.documents.security import DocumentSecurityError
from research_navigator.models import Paper, PaperDocument


@dataclass(frozen=True, slots=True)
class PublicIngestResult:
    document: PaperDocument
    cache_hit: bool


def ingest_public_pdf(
    session: Session,
    *,
    settings: Settings,
    paper: Paper,
    candidate: OpenMaterialCandidate,
    fetched: FetchedPDF,
    acquisition_run_id: str,
    storage: DurableStorage | None = None,
) -> PublicIngestResult:
    """Parse and index one approved public PDF, shared across users.

    Rights and identity are checked before any durable write.  The explicit
    query is intentional: SQL NULL unique constraints do not deduplicate
    shared documents reliably across all supported databases.
    """
    if candidate.cache_policy != "shared_durable":
        raise DocumentSecurityError("Public material is not approved for shared caching")
    if candidate.source == "arxiv" and candidate.source_record_id != expected_arxiv_identity(paper):
        raise DocumentSecurityError("Public material identity mismatch")

    existing = session.scalar(
        select(PaperDocument).where(
            PaperDocument.paper_id == paper.id,
            PaperDocument.user_id.is_(None),
            PaperDocument.sha256 == fetched.sha256,
        )
    )
    if existing is not None:
        return PublicIngestResult(document=existing, cache_hit=True)

    if not fetched.data.startswith(b"%PDF-") or len(fetched.data) > settings.max_pdf_bytes:
        raise DocumentSecurityError("Invalid public PDF")
    try:
        parsed = parse_pdf(fetched.data)
    except Exception as exc:
        raise DocumentSecurityError(f"PDF parsing failed: {type(exc).__name__}") from exc
    has_text = any(page.text.strip() for page in parsed.pages)
    source_type = {"arxiv": "arxiv_oa", "openalex": "openalex_oa"}[candidate.source]
    storage_key = f"public/papers/{paper.id}/{fetched.sha256}.pdf"
    resolved_storage = storage or LocalStorage(settings.upload_dir)
    resolved_storage.put(storage_key, fetched.data)
    stored_path = (
        settings.upload_dir / storage_key
        if isinstance(resolved_storage, LocalStorage)
        else storage_key
    )
    document = PaperDocument(
        user_id=None,
        paper_id=paper.id,
        source_type=source_type,
        evidence_level=(
            "open_fulltext"
            if parsed.text_coverage == "succeeded"
            else "partial_fulltext"
            if has_text
            else "not_available"
        ),
        original_filename=f"{source_type}-{paper.id}.pdf",
        stored_path=str(stored_path),
        mime_type=fetched.content_type or "application/pdf",
        sha256=fetched.sha256,
        size_bytes=len(fetched.data),
        page_count=parsed.page_count,
        rights_confirmed=True,
        ingestion_version="pdf-v4-public-shared",
        material_binding_json=json.dumps(
            bind_material(
                paper_id=paper.id,
                arxiv_id=expected_arxiv_identity(paper),
                doi=paper.doi,
                sha256=fetched.sha256,
                parsed=parsed,
            )
        ),
        source_url=fetched.final_url,
        source_record_id=candidate.source_record_id,
        rights_basis=candidate.rights_basis,
        license=candidate.license,
        retrieved_at=datetime.now(UTC),
        response_hash=fetched.response_hash,
        acquisition_run_id=acquisition_run_id,
        parse_status=parsed.text_coverage,
    )
    session.add(document)
    session.flush()
    if has_text:
        index_document(session, document=document, parsed=parsed)
    return PublicIngestResult(document=document, cache_hit=False)
