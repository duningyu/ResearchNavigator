"""User-authorized PDF upload and evidence retrieval endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from research_navigator.data_plane.storage import LocalStorage
from research_navigator.deps import get_current_user, get_db
from research_navigator.documents.index import index_document, search_document_chunks
from research_navigator.documents.parser import parse_pdf
from research_navigator.documents.security import DocumentSecurityError, validate_pdf_upload
from research_navigator.models import Paper, PaperChunk, PaperDocument, User
from research_navigator.schemas.documents import (
    ContentStatus,
    DocumentRead,
    RetrievalHitRead,
    RetrievalRequest,
    RetrievalResponse,
)

router = APIRouter(tags=["documents"])


def _paper_or_404(session: Session, paper_id: int) -> Paper:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


def _document_read(session: Session, row: PaperDocument) -> DocumentRead:
    chunk_count = (
        session.scalar(select(func.count(PaperChunk.id)).where(PaperChunk.document_id == row.id))
        or 0
    )
    return DocumentRead(
        id=row.id,
        paper_id=row.paper_id,
        original_filename=row.original_filename,
        evidence_level=row.evidence_level,
        source_type=row.source_type,
        sha256=row.sha256,
        size_bytes=row.size_bytes,
        page_count=row.page_count,
        chunk_count=int(chunk_count),
        parse_status=row.parse_status,
        source_url=row.source_url,
        source_record_id=row.source_record_id,
        rights_basis=row.rights_basis,
        license=row.license,
        retrieved_at=row.retrieved_at,
        acquisition_run_id=row.acquisition_run_id,
        created_at=row.created_at,
    )


@router.post(
    "/papers/{paper_id}/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED
)
async def upload_paper(
    paper_id: int,
    request: Request,
    file: UploadFile = File(...),
    rights_confirmed: bool = Form(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> DocumentRead:
    _paper_or_404(session, paper_id)
    if not rights_confirmed:
        raise HTTPException(status_code=400, detail="Rights confirmation is required")
    settings = request.app.state.settings
    max_pdf_bytes = settings.max_pdf_bytes
    if settings.public_demo_mode:
        max_pdf_bytes = min(max_pdf_bytes, settings.public_demo_max_upload_mb * 1024 * 1024)
    data = await file.read(max_pdf_bytes + 1)
    try:
        validated = validate_pdf_upload(
            file.filename or "paper.pdf",
            file.content_type,
            data,
            max_bytes=max_pdf_bytes,
        )
        parsed = parse_pdf(data)
    except DocumentSecurityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"PDF parsing failed: {type(exc).__name__}"
        ) from exc

    storage_key = f"{user.id}/{paper_id}/{validated.sha256}.pdf"
    storage = LocalStorage(request.app.state.settings.upload_dir)
    stored_path = request.app.state.settings.upload_dir / storage_key
    if not stored_path.exists():
        storage.put(storage_key, data)

    existing = session.scalar(
        select(PaperDocument).where(
            PaperDocument.user_id == user.id,
            PaperDocument.paper_id == paper_id,
            PaperDocument.sha256 == validated.sha256,
        )
    )
    if existing is not None:
        return _document_read(session, existing)

    document = PaperDocument(
        user_id=user.id,
        paper_id=paper_id,
        source_type="user_upload",
        evidence_level="user_uploaded_fulltext",
        original_filename=validated.safe_filename,
        stored_path=str(stored_path),
        mime_type="application/pdf",
        sha256=validated.sha256,
        size_bytes=validated.size_bytes,
        page_count=parsed.page_count,
        rights_confirmed=True,
        ingestion_version="pdf-v1",
    )
    session.add(document)
    session.flush()
    index_document(session, document=document, parsed=parsed)
    session.commit()
    session.refresh(document)
    return _document_read(session, document)


@router.get("/papers/{paper_id}/documents", response_model=list[DocumentRead])
def list_documents(
    paper_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[DocumentRead]:
    _paper_or_404(session, paper_id)
    documents = list(
        session.scalars(
            select(PaperDocument)
            .where(
                PaperDocument.paper_id == paper_id,
                or_(PaperDocument.user_id == user.id, PaperDocument.user_id.is_(None)),
            )
            .order_by(PaperDocument.created_at.desc(), PaperDocument.id.desc())
        )
    )
    return [_document_read(session, row) for row in documents]


@router.get("/papers/{paper_id}/content-status", response_model=ContentStatus)
def content_status(
    paper_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ContentStatus:
    paper = _paper_or_404(session, paper_id)
    documents = list(
        session.scalars(
            select(PaperDocument)
            .where(
                PaperDocument.paper_id == paper_id,
                or_(PaperDocument.user_id == user.id, PaperDocument.user_id.is_(None)),
            )
            .order_by(PaperDocument.created_at.desc())
        )
    )
    successful_documents = [row for row in documents if row.parse_status == "succeeded"]
    if successful_documents:
        evidence_level = successful_documents[0].evidence_level
    elif paper.abstract:
        evidence_level = "abstract_only"
    else:
        evidence_level = "metadata_only"
    return ContentStatus(
        paper_id=paper_id,
        evidence_level=evidence_level,
        documents=[_document_read(session, row) for row in documents],
    )


@router.post("/papers/{paper_id}/retrieve", response_model=RetrievalResponse)
def retrieve(
    paper_id: int,
    payload: RetrievalRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> RetrievalResponse:
    _paper_or_404(session, paper_id)
    hits = search_document_chunks(
        session, user_id=user.id, paper_id=paper_id, query=payload.query, top_k=payload.top_k
    )
    return RetrievalResponse(
        paper_id=paper_id,
        query=payload.query,
        hits=[
            RetrievalHitRead(
                chunk_id=hit.chunk_id,
                text=hit.text,
                section=hit.section,
                score=hit.score,
                lexical_score=hit.lexical_score,
                dense_score=hit.dense_score,
                evidence_level=hit.evidence_level,
                citation=hit.citation,
            )
            for hit in hits
        ],
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Response:
    document = session.scalar(
        select(PaperDocument).where(
            PaperDocument.id == document_id, PaperDocument.user_id == user.id
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    stored_path = Path(document.stored_path).resolve()
    upload_root = Path(request.app.state.settings.upload_dir).resolve()
    if not stored_path.is_relative_to(upload_root):
        raise HTTPException(status_code=409, detail="Stored document path is outside upload root")
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        session.execute(
            text("DELETE FROM paper_chunks_fts WHERE document_id = :document_id"),
            {"document_id": str(document.id)},
        )
    session.delete(document)
    session.commit()
    try:
        relative_key = stored_path.relative_to(upload_root).as_posix()
        LocalStorage(upload_root).delete(relative_key)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Document metadata deleted but file cleanup failed: {type(exc).__name__}",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
