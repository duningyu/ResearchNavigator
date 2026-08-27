from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PlanCreate(BaseModel):
    project_id: int
    gap_id: int
    title: str | None = Field(default=None, max_length=240)


class PlanItemUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(pending|in_progress|done|blocked)$")
    notes: str | None = Field(default=None, max_length=4000)


class PlanItemRead(BaseModel):
    id: int
    category: str
    title: str
    description: str
    sequence: int
    status: str
    notes: str | None
    created_at: datetime


class ResearchPlanRead(BaseModel):
    id: int
    project_id: int
    gap_id: int | None
    title: str
    objective: str
    status: str
    items: list[PlanItemRead]
    created_at: datetime
