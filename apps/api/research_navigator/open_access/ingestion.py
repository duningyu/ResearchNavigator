"""Persist a policy-approved OA PDF through the existing parser and indexer."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.config import Settings
from research_navigator.data_plane.storage import DurableStorage, LocalStorage
from research_navigator.documents.index import index_document
from research_navigator.documents.parser import parse_pdf
from research_navigator.documents.security import DocumentSecurityError, validate_pdf_upload
from research_navigator.models import Paper, PaperDocument
from research_navigator.open_access.base import OpenAccessCandidate
from research_navigator.open_access.fetcher import PdfFetchResult


def ingest_open_access_pdf(
    session: Session,
    *,
    settings: Settings,
    user_id: int,
    paper: Paper,
    candidate: OpenAccessCandidate,
    fetched: PdfFetchResult,
    acquisition_run_id: str,
    user_confirmed_limited_license: bool = False,
    storage: DurableStorage | None = None,
) -> PaperDocument:
    if candidate.access_decision == "requires_user_confirmation":
        if not user_confirmed_limited_license:
            raise DocumentSecurityError("Limited OA license requires user confirmation")
        rights_basis = "user_confirmed_limited_oa_license"
    elif candidate.access_decision == "auto_ingest":
        rights_basis = "explicit_open_license"
    else:
        raise DocumentSecurityError("OA policy does not permit ingestion")

    existing = session.scalar(
        select(PaperDocument).where(
            PaperDocument.user_id == user_id,
            PaperDocument.paper_id == paper.id,
            PaperDocument.sha256 == fetched.sha256,
        )
    )
    if existing is not None:
        return existing

    source_slug = candidate.source.replace("/", "-")[:40]
    validated = validate_pdf_upload(
        f"{source_slug}-{candidate.source_record_id}.pdf",
        fetched.content_type,
        fetched.data,
        max_bytes=settings.max_pdf_bytes,
    )
    try:
        parsed = parse_pdf(fetched.data)
    except Exception as exc:
        raise DocumentSecurityError(f"PDF parsing failed: {type(exc).__name__}") from exc
    has_text = any(page.text.strip() for page in parsed.pages)

    storage_key = f"{user_id}/{paper.id}/oa/{validated.sha256}.pdf"
    resolved_storage = storage or LocalStorage(settings.upload_dir)
    resolved_storage.put(storage_key, fetched.data)
    stored_path = (
        settings.upload_dir / storage_key
        if isinstance(resolved_storage, LocalStorage)
        else None
    )

    document = PaperDocument(
        user_id=user_id,
        paper_id=paper.id,
        source_type="open_access_repository",
        evidence_level="open_fulltext" if has_text else "not_available",
        original_filename=validated.safe_filename,
        stored_path=str(stored_path or storage_key),
        mime_type=fetched.content_type,
        sha256=validated.sha256,
        size_bytes=validated.size_bytes,
        page_count=parsed.page_count,
        rights_confirmed=True,
        ingestion_version="pdf-v2-oa",
        source_url=fetched.final_url,
        source_record_id=candidate.source_record_id,
        rights_basis=rights_basis,
        license=candidate.normalized_license or candidate.license,
        retrieved_at=fetched.retrieved_at,
        response_hash=fetched.response_hash,
        acquisition_run_id=acquisition_run_id,
        parse_status="succeeded" if has_text else "failed_no_extractable_text",
    )
    session.add(document)
    session.flush()
    if has_text:
        index_document(session, document=document, parsed=parsed)
    return document
