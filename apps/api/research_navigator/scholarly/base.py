"""Shared scholarly records and adapter contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PaperAuthor(BaseModel):
    name: str
    orcid: str | None = None
    affiliations: list[str] = Field(default_factory=list)
    source_author_id: str | None = None


class SourceProvenance(BaseModel):
    source: str
    source_id: str
    source_url: str | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_hash: str | None = None
    is_fixture: bool = False
    raw_payload: dict[str, Any] | None = None


class PaperRecord(BaseModel):
    title: str
    normalized_title: str | None = None
    translated_title: str | None = None
    abstract: str | None = None
    publication_year: int | None = None
    publication_date: date | None = None
    authors: list[PaperAuthor] = Field(default_factory=list)
    venue: str | None = None
    venue_type: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)
    source_urls: list[str] = Field(default_factory=list)
    publisher_url: str | None = None
    pdf_url: str | None = None
    open_access_status: str | None = None
    citation_count: int | None = None
    reference_count: int | None = None
    fields_of_study: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    source_provenance: list[SourceProvenance] = Field(default_factory=list)
    abstract_provenance: SourceProvenance | None = None
    source_score: float | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    year_from: int | None = Field(default=None, ge=1800, le=2200)
    year_to: int | None = Field(default=None, ge=1800, le=2200)
    open_access_only: bool = False
    sources: list[str] = Field(default_factory=list)
    project_id: int | None = None


class SourceStatus(BaseModel):
    status: Literal["ok", "error", "disabled", "not_configured", "rate_limited"]
    result_count: int = 0
    detail: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AdapterSearchResult(BaseModel):
    records: list[PaperRecord] = Field(default_factory=list)
    status: SourceStatus


class ScholarlyAdapter(ABC):
    name: str
    supports_evidence_acquisition: bool = False

    @abstractmethod
    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        raise NotImplementedError

    async def health(self) -> SourceStatus:
        return SourceStatus(status="ok")

    async def resolve_exact(self, doi: str) -> PaperRecord | None:
        return None
