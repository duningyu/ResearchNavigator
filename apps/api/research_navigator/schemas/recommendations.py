from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from research_navigator.schemas.search import PaperRead


class RecommendationRefreshRequest(BaseModel):
    project_id: int | None = None
    limit: int = Field(default=20, ge=1, le=100)


class ReadingRecommendation(BaseModel):
    verdict: Literal["priority_read", "method_reference", "not_priority", "insufficient_evidence"]
    rationale: str
    task_match: Literal["matched", "mismatched", "unknown"]
    evidence_level: Literal["metadata", "abstract", "full_text"]
    applicability: str
    missing_information: list[str]
    evidence_refs: list[dict[str, object]]
    research_profile_identity: str
    paper_identity: str
    material_identity: str
    is_current: bool = True
    invalidation_reason: str | None = None


class RecommendationRead(BaseModel):
    id: int
    project_id: int | None
    category: str
    score: float
    reason: str
    evidence: dict[str, object]
    recommendation_version: str
    paper: PaperRead
    created_at: datetime
    reading_recommendation: ReadingRecommendation
