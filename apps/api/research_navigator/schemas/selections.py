from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from research_navigator.schemas.search import PaperRead


class PaperSetCreate(BaseModel):
    project_id: int | None = None
    purpose: str = Field(pattern="^(compare|gap|manual)$")
    name: str = Field(min_length=1, max_length=240)
    paper_ids: list[int] = Field(min_length=1, max_length=100)
    source_kind: str = Field(
        default="explicit", pattern="^(explicit|search_session|favorites|manual)$"
    )


class PaperSetRead(BaseModel):
    id: int
    project_id: int | None
    purpose: str
    name: str
    source_kind: str
    paper_ids: list[int]
    papers: list[PaperRead]
    created_at: datetime
