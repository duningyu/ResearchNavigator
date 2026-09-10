"""User-authorized PDF upload and evidence retrieval endpoints."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

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
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from research_navigator.config import Settings
from research_navigator.data_plane.storage import DurableStorage, LocalStorage, R2Storage
from research_navigator.deps import get_current_user, get_db
from research_navigator.documents.index import index_document, search_document_chunks
from research_navigator.documents.material_binding import bind_material, expected_arxiv_identity
from research_navigator.documents.parser import parse_pdf
from research_navigator.documents.security import DocumentSecurityError, validate_pdf_upload
from research_navigator.idempotency import replay_snapshot, store_snapshot
from research_navigator.models import Paper, PaperChunk, PaperDocument, User
from research_navigator.schemas.documents import (
    ContentStatus,
    DocumentRead,
    RetrievalHitRead,
    RetrievalRequest,
    RetrievalResponse,
)
from research_navigator.uploads import (
    FIXED_R2_BUCKET,
    MAX_PRESIGN_TTL_SECONDS,
    PRESIGN_TTL_SECONDS,
    issue_completion_token,
    validate_presign_metadata,
    verify_completion_token,
)

router = APIRouter(tags=["documents"])


class PresignUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    content_type: str
    size_bytes: int
    sha256: str


class PresignUploadResponse(BaseModel):
    upload_method: Literal["PUT"]
    presigned_url: str
    required_headers: dict[str, str]
    completion_token: str
    expires_at: datetime


class FinalizeUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completion_token: str = Field(min_length=1)


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
        material_binding=json.loads(row.material_binding_json or "{}"),
        source_url=row.source_url,
        source_record_id=row.source_record_id,
        rights_basis=row.rights_basis,
        license=row.license,
        retrieved_at=row.retrieved_at,
        acquisition_run_id=row.acquisition_run_id,
        created_at=row.created_at,
    )


def _effective_max_pdf_bytes(settings: Settings) -> int:
    max_pdf_bytes = settings.max_pdf_bytes
    if settings.public_demo_mode:
        max_pdf_bytes = min(max_pdf_bytes, settings.public_demo_max_upload_mb * 1024 * 1024)
    return max_pdf_bytes


def _claim_int(claims: dict[str, object], name: str) -> int:
    value = claims[name]
    if not isinstance(value, (int, str, float)):
        raise ValueError(name)
    return int(value)


def _ingest_pdf_bytes(
    *,
    session: Session,
    storage: DurableStorage,
    settings: Settings,
    user: User,
    paper_id: int,
    filename: str,
    content_type: str | None,
    data: bytes,
    rights_confirmed: bool,
    storage_key: str,
    store_object: bool,
) -> DocumentRead:
    if not rights_confirmed:
        raise HTTPException(status_code=400, detail="Rights confirmation is required")
    try:
        validated = validate_pdf_upload(
            filename, content_type, data, max_bytes=_effective_max_pdf_bytes(settings)
        )
        parsed = parse_pdf(data)
    except DocumentSecurityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"PDF parsing failed: {type(exc).__name__}"
        ) from exc
    if store_object:
        storage.put(storage_key, data)
    stored_path = settings.upload_dir / storage_key if settings.storage_backend == "local" else None
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
        evidence_level=(
            "user_uploaded_fulltext"
            if parsed.text_coverage == "succeeded"
            else "partial_fulltext"
            if parsed.text_coverage == "partial"
            else "not_available"
        ),
        original_filename=validated.safe_filename,
        stored_path=str(stored_path or storage_key),
        mime_type="application/pdf",
        sha256=validated.sha256,
        size_bytes=validated.size_bytes,
        page_count=parsed.page_count,
        rights_confirmed=True,
        ingestion_version="pdf-v2-coverage",
        material_binding_json=json.dumps(bind_material(
            paper_id=paper_id, arxiv_id=expected_arxiv_identity(_paper_or_404(session, paper_id)),
            doi=_paper_or_404(session, paper_id).doi, sha256=validated.sha256, parsed=parsed,
        )),
        parse_status=parsed.text_coverage,
    )
    session.add(document)
    session.flush()
    index_document(session, document=document, parsed=parsed)
    session.commit()
    session.refresh(document)
    return _document_read(session, document)


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
    settings = request.app.state.settings
    data = await file.read(_effective_max_pdf_bytes(settings) + 1)
    return _ingest_pdf_bytes(
        session=session,
        storage=request.app.state.storage,
        settings=settings,
        user=user,
        paper_id=paper_id,
        filename=file.filename or "paper.pdf",
        content_type=file.content_type,
        data=data,
        rights_confirmed=rights_confirmed,
        storage_key=f"{user.id}/{paper_id}/{hashlib.sha256(data).hexdigest()}.pdf",
        store_object=True,
    )


@router.post("/papers/{paper_id}/uploads/presign", response_model=PresignUploadResponse)
def presign_upload(
    paper_id: int,
    payload: PresignUploadRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> PresignUploadResponse:
    settings = request.app.state.settings
    if settings.storage_backend != "r2":
        raise HTTPException(status_code=409, detail="Presigned uploads require R2 storage")
    storage = request.app.state.storage
    if not isinstance(storage, R2Storage) or storage.bucket != FIXED_R2_BUCKET:
        raise HTTPException(status_code=503, detail="Configured R2 bucket is not approved")
    _paper_or_404(session, paper_id)
    try:
        metadata = validate_presign_metadata(
            filename=payload.filename,
            content_type=payload.content_type,
            size_bytes=payload.size_bytes,
            sha256=payload.sha256,
            max_bytes=_effective_max_pdf_bytes(settings),
        )
    except DocumentSecurityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not settings.upload_signing_secret:
        raise HTTPException(status_code=503, detail="Upload signing is not configured")
    key = f"uploads/{user.id}/{uuid.uuid4().hex}/{metadata.sha256}.pdf"
    expires_at = datetime.now(UTC) + timedelta(seconds=PRESIGN_TTL_SECONDS)
    try:
        url = storage.generate_presigned_upload(
            key=key,
            content_type=metadata.content_type,
            sha256=metadata.sha256,
            expires_in=min(PRESIGN_TTL_SECONDS, MAX_PRESIGN_TTL_SECONDS),
        )
    except (NotImplementedError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail="R2 presigned upload is unavailable") from exc
    token = issue_completion_token(
        secret=settings.upload_signing_secret,
        claims={
            "user_id": user.id,
            "paper_id": paper_id,
            "key": key,
            "filename": metadata.filename,
            "content_type": metadata.content_type,
            "size_bytes": metadata.size_bytes,
            "sha256": metadata.sha256,
            "exp": int(expires_at.timestamp()),
        },
    )
    return PresignUploadResponse(
        upload_method="PUT",
        presigned_url=url,
        required_headers={
            "Content-Type": metadata.content_type,
            "x-amz-meta-sha256": metadata.sha256,
        },
        completion_token=token,
        expires_at=expires_at,
    )


@router.post("/papers/{paper_id}/uploads/finalize", response_model=DocumentRead)
def finalize_upload(
    paper_id: int,
    payload: FinalizeUploadRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> DocumentRead:
    settings = request.app.state.settings
    storage = request.app.state.storage
    if settings.storage_backend != "r2" or not isinstance(storage, R2Storage):
        raise HTTPException(status_code=409, detail="Finalization requires R2 storage")
    if not settings.upload_signing_secret:
        raise HTTPException(status_code=503, detail="Upload signing is not configured")
    try:
        claims = verify_completion_token(
            secret=settings.upload_signing_secret, token=payload.completion_token
        )
    except DocumentSecurityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        claim_user_id = _claim_int(claims, "user_id")
        claim_paper_id = _claim_int(claims, "paper_id")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid upload completion token") from exc
    if claim_user_id != user.id or claim_paper_id != paper_id:
        raise HTTPException(status_code=403, detail="Upload does not belong to this user")
    key = claims.get("key")
    expected_sha = claims.get("sha256")
    if not isinstance(key, str) or not isinstance(expected_sha, str):
        raise HTTPException(status_code=400, detail="Invalid upload completion token")
    idem_payload = {"paper_id": paper_id, "key": key, "sha256": expected_sha}
    replay = replay_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="upload_finalize",
        payload=idem_payload,
    )
    if replay is not None:
        return DocumentRead.model_validate(replay)
    try:
        stats = storage.stat(key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Uploaded object was not found") from exc
    try:
        expected_size = _claim_int(claims, "size_bytes")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid upload completion token") from exc
    content_length = stats.get("ContentLength")
    if content_length is not None:
        if not isinstance(content_length, (int, str, float)):
            raise HTTPException(status_code=502, detail="Invalid storage metadata")
        if int(content_length) != expected_size:
            raise HTTPException(status_code=400, detail="Uploaded object size does not match claim")
    if stats.get("ContentType") is not None and str(stats["ContentType"]) != str(
        claims.get("content_type")
    ):
        raise HTTPException(status_code=400, detail="Uploaded object type does not match claim")
    metadata = stats.get("Metadata")
    if isinstance(metadata, dict) and metadata.get("sha256") not in {None, expected_sha}:
        raise HTTPException(
            status_code=400, detail="Uploaded object hash metadata does not match claim"
        )
    data = storage.get(key)
    if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_sha:
        raise HTTPException(
            status_code=400, detail="Uploaded object content hash does not match claim"
        )
    _paper_or_404(session, paper_id)
    result = _ingest_pdf_bytes(
        session=session,
        storage=storage,
        settings=settings,
        user=user,
        paper_id=paper_id,
        filename=str(claims.get("filename", "paper.pdf")),
        content_type=str(claims.get("content_type")),
        data=data,
        rights_confirmed=True,
        storage_key=key,
        store_object=False,
    )
    store_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="upload_finalize",
        payload=idem_payload,
        resource_type="paper_document",
        resource_id=result.id,
        response_snapshot=result.model_dump(mode="json"),
    )
    return result


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
    successful_documents = [
        row for row in documents if row.parse_status in {"succeeded", "partial"}
    ]
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
    if request.app.state.settings.storage_backend != "local":
        session.delete(document)
        session.commit()
        request.app.state.storage.delete(document.stored_path)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
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
