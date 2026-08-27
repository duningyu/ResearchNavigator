from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceWorkflowCreate(BaseModel):
    project_id: int | None = None
    sources: list[str] = Field(default_factory=list, max_length=8)
    allow_oa_fulltext: bool = True
    confirm_limited_license: bool = False


class EvidenceWorkflowEventRead(BaseModel):
    id: int
    event_type: str
    detail: dict[str, object]
    created_at: datetime


class EvidenceWorkflowRead(BaseModel):
    id: int
    paper_id: int
    project_id: int | None
    status: str
    payload: dict[str, object]
    result: dict[str, object]
    error: str | None
    strongest_evidence: str
    attempt_count: int
    max_attempts: int
    started_at: datetime | None
    finished_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    terminal: bool
    events: list[EvidenceWorkflowEventRead] = Field(default_factory=list)
