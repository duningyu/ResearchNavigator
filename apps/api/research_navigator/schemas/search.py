from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from research_navigator.scholarly.base import (
    PaperAuthor,
    SearchRequest,
    SourceProvenance,
    SourceStatus,
)


class SearchPaperRequest(SearchRequest):
    mode: Literal["auto", "precise", "discovery"] = "auto"


class RankingMetadata(BaseModel):
    label: str
    relevance: float
    rank_score: float
    relevance_band: int
    position: int



class PaperRead(BaseModel):
    id: int
    title: str
    normalized_title: str
    translated_title: str | None
    abstract: str | None
    publication_year: int | None
    publication_date: str | None
    authors: list[PaperAuthor]
    venue: str | None
    venue_type: str | None
    doi: str | None
    arxiv_id: str | None
    external_ids: dict[str, str]
    source_urls: list[str]
    publisher_url: str | None
    pdf_url: str | None
    open_access_status: str | None
    citation_count: int | None
    reference_count: int | None
    fields_of_study: list[str]
    concepts: list[str]
    keywords: list[str]
    source_provenance: list[SourceProvenance]
    is_fixture: bool
    abstract_evidence_verified: bool
    ranking: RankingMetadata | None = None


class SearchResponse(BaseModel):
    session_id: int
    result_count: int
    source_status: dict[str, SourceStatus]
    search_mode: str
    diversity_seed: str | None
    ranking_rule_version: str
    composition: dict[str, object]
    papers: list[PaperRead]


class SearchSessionRead(BaseModel):
    id: int
    project_id: int | None
    query: str
    filters: dict[str, object]
    source_status: dict[str, SourceStatus]
    result_ids: list[int]
    result_count: int
    search_mode: str
    diversity_seed: str | None
    ranking_rule_version: str
    composition: dict[str, object]
    created_at: datetime


class PaperResolveRequest(BaseModel):
    doi: str | None = None
    arxiv_id: str | None = None
    title: str | None = None
    publication_year: int | None = Field(default=None, ge=1800, le=2200)
    sources: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_identifier(self) -> PaperResolveRequest:
        if not any((self.doi, self.arxiv_id, self.title)):
            raise ValueError("At least one of doi, arxiv_id, or title is required")
        return self


class RelatedPaperRead(BaseModel):
    paper: PaperRead
    score: float
    rationale: str
    shared_terms: list[str]
