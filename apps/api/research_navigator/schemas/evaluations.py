from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class EvaluationTaskCreate(BaseModel):
    task_key: str = Field(min_length=1, max_length=160)
    paper_id: int | None = None
    baseline_payload: dict[str, Any]
    candidate_payload: dict[str, Any]
    position: int = Field(ge=0)


class EvaluationStudyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    description: str | None = None
    study_version: str = Field(min_length=1, max_length=80)
    randomized_seed: str = Field(min_length=8, max_length=64)
    protocol: dict[str, Any] = Field(default_factory=dict)
    tasks: list[EvaluationTaskCreate] = Field(min_length=1, max_length=500)


class EvaluationTaskRead(BaseModel):
    id: int
    task_key: str
    paper_id: int | None
    position: int


class EvaluationStudyRead(BaseModel):
    id: int
    name: str
    description: str | None
    status: str
    study_version: str
    frozen_input_hash: str | None
    expert_outcome_validation: str
    randomized_seed: str
    protocol: dict[str, Any]
    tasks: list[EvaluationTaskRead] = Field(default_factory=list)


class EvaluationAssignmentCreate(BaseModel):
    expert_user_id: int
    is_simulated: bool = False
    task_ids: list[int] | None = None


class EvaluationVariantRead(BaseModel):
    label: Literal["A", "B"]
    payload: dict[str, Any]


class EvaluationAssignmentRead(BaseModel):
    id: int
    study_id: int
    task_id: int
    task_key: str
    status: str
    is_simulated: bool
    variants: list[EvaluationVariantRead]
    assigned_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class EvaluationRatingCreate(BaseModel):
    evidence_correctness: float = Field(ge=1, le=5)
    evidence_sufficiency: float = Field(ge=1, le=5)
    citation_usefulness: float = Field(ge=1, le=5)
    missing_field_correctness: float = Field(ge=1, le=5)
    preference: Literal["A", "B", "tie"]
    comments: str | None = Field(default=None, max_length=5000)


class EvaluationRatingRead(BaseModel):
    id: int
    assignment_id: int
    preference: str
    duration_seconds: int
    submitted_at: datetime


class EvaluationResultRead(BaseModel):
    study_id: int
    metrics: dict[str, Any]
    real_expert_count: int
    simulated_count: int
    validation_status: str
    claim_boundary: str
