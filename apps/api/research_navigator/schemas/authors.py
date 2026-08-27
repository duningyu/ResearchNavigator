from __future__ import annotations

from pydantic import BaseModel, Field


class AuthorCardRead(BaseModel):
    id: int
    canonical_name: str
    orcid: str | None
    openalex_id: str | None
    semantic_scholar_id: str | None
    affiliations: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    works_count: int | None
    citation_count: int | None
    homepage: str | None
    identity_status: str
    provenance: list[dict[str, object]] = Field(default_factory=list)
    position: int | None = None
    credit_roles: list[str] = Field(default_factory=list)
