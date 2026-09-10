from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class AbstractTranslationRead(BaseModel):
    paper_id: int
    original_abstract: str | None
    translated_abstract: str | None
    status: Literal["ready", "failed", "partial", "unavailable"]
    source_abstract_sha256: str | None
    target_language: str
    pipeline_version: str
    fallback_reason: str | None = None
    cache_hit: bool = False
