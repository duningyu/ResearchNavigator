"""Shared open-access resolution contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

AccessDecision = Literal[
    "auto_ingest", "requires_user_confirmation", "link_only", "rejected"
]


class PaperIdentity(BaseModel):
    doi: str | None = None
    arxiv_id: str | None = None
    title: str
    publication_year: int | None = None


class OpenAccessCandidate(BaseModel):
    source: str
    source_record_id: str
    landing_url: str | None = None
    pdf_url: str | None = None
    license: str | None = None
    normalized_license: str | None = None
    host_type: str | None = None
    version: str | None = None
    is_oa: bool = False
    requires_auth: bool = False
    access_decision: AccessDecision = "link_only"
    rejection_reason: str | None = None
    provenance_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpenAccessResolution(BaseModel):
    candidates: list[OpenAccessCandidate] = Field(default_factory=list)
    selected: OpenAccessCandidate | None = None
    source_status: dict[str, str] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)


class OpenAccessClient(Protocol):
    name: str

    async def resolve(self, identity: PaperIdentity) -> list[OpenAccessCandidate]: ...


def payload_hash(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
