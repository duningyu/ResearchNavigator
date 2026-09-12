from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PlanCreate(BaseModel):
    plan_kind: Literal["reading", "exploration", "confirmed_gap", "manual"] | None = None
    project_id: int
    gap_id: int | None = None
    title: str | None = Field(default=None, max_length=240)
    objective: str | None = Field(default=None, min_length=1, max_length=4000)


class PlanItemUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(pending|in_progress|done|blocked|skipped)$")
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    notes: str | None = Field(default=None, max_length=4000)
    purpose: str | None = Field(default=None, max_length=4000)
    expected_output: str | None = Field(default=None, max_length=4000)


class PlanItemRead(BaseModel):
    id: int
    category: str
    title: str
    description: str
    sequence: int
    status: str
    notes: str | None
    purpose: str | None = None
    expected_output: str | None = None
    created_at: datetime


class ResearchPlanRead(BaseModel):
    review_required: bool = False
    review_reason: str | None = None
    id: int
    project_id: int
    gap_id: int | None
    plan_kind: Literal["reading", "exploration", "confirmed_gap", "manual"]
    title: str
    objective: str
    status: str
    items: list[PlanItemRead]
    created_at: datetime
