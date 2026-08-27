from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AbstractBackfillCreate(BaseModel):
    dry_run: bool = True
    batch_size: int = Field(default=25, ge=1, le=500)
    sources: list[str] = Field(default_factory=list, max_length=8)


class AbstractBackfillRead(BaseModel):
    id: int
    status: str
    payload: dict[str, object]
    result: dict[str, object]
    error: str | None
    attempt_count: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancelled_at: datetime | None
    terminal: bool
