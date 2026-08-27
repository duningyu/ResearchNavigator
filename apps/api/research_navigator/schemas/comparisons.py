from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ComparisonCreate(BaseModel):
    project_id: int
    paper_set_id: int


class ComparisonPaper(BaseModel):
    id: int
    title: str
    publication_year: int | None
    venue: str | None
    evidence_level: str


class ComparisonCell(BaseModel):
    paper_id: int
    value: Any = None
    evidence_state: Literal["evidenced", "insufficient_evidence", "unknown"]
    citations: list[dict[str, Any]]


class ComparisonRow(BaseModel):
    key: str
    label: str
    cells: list[ComparisonCell]


class ComparisonRead(BaseModel):
    id: int
    project_id: int
    paper_set_id: int
    direction_snapshot: dict[str, Any]
    papers: list[ComparisonPaper]
    rows: list[ComparisonRow]
    analysis_version: str
    evidence_hash: str
    created_at: datetime
