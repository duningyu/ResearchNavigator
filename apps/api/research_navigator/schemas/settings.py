from __future__ import annotations

from pydantic import BaseModel, Field


class UserSettingsUpdate(BaseModel):
    default_result_count: int = Field(default=50, ge=10, le=50)
    default_page_size: int = Field(default=10, ge=5, le=50)
    preferred_sources: list[str] = Field(default_factory=list, max_length=20)
    default_open_access_only: bool = False
    display_language: str = Field(default="zh-CN", max_length=20)
    analysis_execution_preference: str = Field(
        default="synchronous", pattern="^(synchronous|queued)$"
    )


class UserSettingsRead(UserSettingsUpdate):
    pass


class AdminRuntimeConfig(BaseModel):
    source_health_timeout_seconds: float = Field(default=5.0, ge=0.5, le=30.0)
    worker_max_attempts_default: int = Field(default=3, ge=1, le=10)


class AdminConfigStatus(BaseModel):
    semantic_scholar_key_configured: bool
    openalex_api_key_configured: bool
    llm_key_configured: bool
    analysis_provider: str
    analysis_prompt_version: str

