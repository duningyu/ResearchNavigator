from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    job_type: str = Field(min_length=1, max_length=80)
    payload: dict[str, object] = Field(default_factory=dict)
    project_id: int | None = None


class JobRead(BaseModel):
    id: int
    project_id: int | None
    job_type: str
    status: str
    payload: dict[str, object]
    result: dict[str, object]
    error: str | None
    attempt_count: int
    max_attempts: int
    started_at: datetime | None
    finished_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    terminal: bool


class JobEventRead(BaseModel):
    id: int
    event_type: str
    detail: dict[str, object]
    created_at: datetime


class SourceHealthRead(BaseModel):
    name: str
    status: str
    enabled: bool
    configured: bool
    detail: str | None = None
    checked_at: datetime
    cooldown_until: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
