from __future__ import annotations

from pydantic import BaseModel, Field


class DirectionClusterCreate(BaseModel):
    paper_ids: list[int] = Field(min_length=1, max_length=500)
    threshold: float = Field(default=0.2, ge=0.0, le=1.0)


class DirectionClusterMemberRead(BaseModel):
    paper_id: int
    cluster_id: int | None
    cluster_key: str | None
    similarity: float
    is_unclustered: bool


class DirectionClusterRead(BaseModel):
    id: int
    cluster_key: str
    label: str
    terms: list[str]
    evidence_distribution: dict[str, int]


class DirectionClusterRunRead(BaseModel):
    id: int
    project_id: int
    algorithm_version: str
    parameters: dict[str, object]
    input_hash: str
    status: str
    disclaimer: str
    clusters: list[DirectionClusterRead] = Field(default_factory=list)
    members: list[DirectionClusterMemberRead] = Field(default_factory=list)
