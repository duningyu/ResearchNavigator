from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DocumentRead(BaseModel):
    id: int
    paper_id: int
    original_filename: str
    evidence_level: str
    source_type: str
    sha256: str
    size_bytes: int
    page_count: int
    chunk_count: int
    parse_status: str = "succeeded"
    source_url: str | None = None
    source_record_id: str | None = None
    rights_basis: str | None = None
    license: str | None = None
    retrieved_at: datetime | None = None
    acquisition_run_id: str | None = None
    created_at: datetime


class ContentStatus(BaseModel):
    paper_id: int
    evidence_level: str
    documents: list[DocumentRead]


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1_000)
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievalHitRead(BaseModel):
    chunk_id: int
    text: str
    section: str
    score: float
    lexical_score: float
    dense_score: float
    evidence_level: str | None
    citation: dict[str, int | str | None]


class RetrievalResponse(BaseModel):
    paper_id: int
    query: str
    hits: list[RetrievalHitRead]
