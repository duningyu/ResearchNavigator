from __future__ import annotations

from pydantic import BaseModel, Field


class DatasetCardRead(BaseModel):
    id: int
    canonical_name: str
    access_url: str | None
    license: str | None
    domain: str | None
    identity_status: str
    provenance: list[dict[str, object]] = Field(default_factory=list)
    mention_id: int | None = None
    paper_id: int | None = None
    analysis_id: int | None = None
    raw_mention: str | None = None
    role: str | None = None
    task: str | None = None
    train_split: str | None = None
    validation_split: str | None = None
    test_split: str | None = None
    metrics: list[str] = Field(default_factory=list)
    evidence_level: str | None = None
    field_citations: dict[str, list[dict[str, object]]] = Field(default_factory=dict)
