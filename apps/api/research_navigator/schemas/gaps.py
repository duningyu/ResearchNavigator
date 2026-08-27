from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class GapGenerateRequest(BaseModel):
    project_id: int
    paper_set_id: int | None = None
    paper_ids: list[int] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def require_selection(self) -> GapGenerateRequest:
        if self.paper_set_id is None and not self.paper_ids:
            raise ValueError("paper_set_id or paper_ids is required")
        return self


class GapChallengeRequest(BaseModel):
    additional_terms: list[str] = Field(default_factory=list, max_length=20)


class GapConfirmRequest(BaseModel):
    confirmed: bool
    note: str | None = Field(default=None, max_length=2000)


class GapCandidateRead(BaseModel):
    id: int
    project_id: int
    paper_set_id: int | None
    direction_snapshot: dict[str, Any]
    gap_type: str
    claim: str
    scope: str
    status: str
    workflow_stage: str
    evidence_matrix: list[dict[str, object]]
    supporting_evidence: list[int]
    adjacent_work: list[int]
    counter_evidence: list[dict[str, object]]
    challenge_queries: list[str]
    data_sources: list[str]
    coverage: dict[str, object]
    confidence: str
    risk_factors: list[str]
    minimal_validation: list[str]
    suggested_research_question: str
    not_novelty_proof: bool
    explanation: dict[str, Any] | None
    challenge_completed_at: datetime | None
    confirmed_at: datetime | None
    human_confirmation_note: str | None
    created_at: datetime
