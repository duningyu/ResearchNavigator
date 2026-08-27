from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from research_navigator.schemas.search import PaperRead


class RecommendationRefreshRequest(BaseModel):
    project_id: int | None = None
    limit: int = Field(default=20, ge=1, le=100)


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
