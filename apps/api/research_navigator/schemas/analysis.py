from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from research_navigator.analysis.matching import WeightedScoreResult
from research_navigator.analysis.reproduction import ReproductionAssessment
from research_navigator.analysis.structured import EvidenceLevel, PaperAnalysisOutput
from research_navigator.schemas.search import PaperRead
from research_navigator.scholarly.base import SourceStatus


class PaperAnalyzeRequest(BaseModel):
    project_id: int | None = None
    provider: Literal["deterministic", "configured"] | None = None


class PaperAnalysisResponse(BaseModel):
    id: int
    paper_id: int
    project_id: int | None
    analysis_version: str
    analysis: PaperAnalysisOutput
    direction_similarity: WeightedScoreResult
    reproduction_assessment: ReproductionAssessment
    created_at: datetime
    analysis_mode: str = "deterministic"
    provider: str = "deterministic"
    model_name: str | None = None
    prompt_version: str | None = None
    fallback_reason: str | None = None


class EvidenceAcquireRequest(BaseModel):
    project_id: int | None = None
    sources: list[str] = Field(default_factory=list, max_length=8)


class EvidenceAcquisitionResponse(BaseModel):
    run_id: str
    outcome: Literal[
        "abstract_acquired",
        "no_matching_evidence",
        "no_eligible_source",
        "source_unavailable",
        "already_sufficient",
    ]
    evidence_level_before: EvidenceLevel
    evidence_level_after: EvidenceLevel
    queried_sources: list[str]
    source_status: dict[str, SourceStatus]
    paper: PaperRead
    analysis: PaperAnalysisResponse
