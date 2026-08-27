from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ResearchProfileUpsert(BaseModel):
    stage: str | None = None
    major: str | None = None
    broad_direction: str | None = None
    keywords: list[str] = Field(default_factory=list)
    excluded_terms: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    compute_constraints: str | None = None


class ResearchProfileRead(ResearchProfileUpsert):
    id: int
    user_id: int


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    description: str | None = None
    broad_direction: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = None
    broad_direction: str | None = None
    status: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    description: str | None
    broad_direction: str | None
    status: str
