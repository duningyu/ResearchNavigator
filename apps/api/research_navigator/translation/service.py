"""Abstract translation orchestration without a production model call.

The service deliberately keeps its cache process-local. Durable translation storage
is not introduced until its schema and invalidation contract are approved.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranslationDraft:
    text: str
    complete: bool = True


class TranslationAdapter(Protocol):
    def translate(
        self, text: str, target_language: str
    ) -> TranslationDraft | dict[str, object]: ...


@dataclass(frozen=True)
class TranslationResult:
    paper_id: int
    original_abstract: str | None
    translated_abstract: str | None
    status: str
    source_abstract_sha256: str | None
    target_language: str
    pipeline_version: str
    fallback_reason: str | None = None
    cache_hit: bool = False


class UnavailableTranslationAdapter:
    """Default adapter: no real provider is called by the local product."""

    def translate(self, text: str, target_language: str) -> TranslationDraft:
        raise RuntimeError("translation adapter is not configured")


class TranslationService:
    def __init__(
        self,
        adapter: TranslationAdapter | None = None,
        *,
        pipeline_version: str = "unconfigured-v1",
    ) -> None:
        self.adapter = adapter or UnavailableTranslationAdapter()
        self.pipeline_version = pipeline_version
        self._cache: dict[tuple[int, str, str, str], TranslationResult] = {}

    def translate(
        self,
        paper_id: int,
        original_abstract: str | None,
        target_language: str,
    ) -> TranslationResult:
        if not original_abstract or not original_abstract.strip():
            return TranslationResult(
                paper_id=paper_id,
                original_abstract=original_abstract,
                translated_abstract=None,
                status="unavailable",
                source_abstract_sha256=None,
                target_language=target_language,
                pipeline_version=self.pipeline_version,
                fallback_reason="original_abstract_unavailable",
            )

        source_hash = hashlib.sha256(original_abstract.encode("utf-8")).hexdigest()
        key = (paper_id, source_hash, target_language, self.pipeline_version)
        cached = self._cache.get(key)
        if cached is not None:
            return TranslationResult(**{**cached.__dict__, "cache_hit": True})

        try:
            draft = self.adapter.translate(original_abstract, target_language)
            if isinstance(draft, dict):
                text = draft.get("text")
                complete = draft.get("complete", True)
            else:
                text = draft.text
                complete = draft.complete
            if not isinstance(text, str) or not text.strip():
                status = "failed"
                reason = "empty_translation"
                translated = None
            elif complete is False:
                status = "partial"
                reason = "partial_translation"
                translated = None
            else:
                status = "ready"
                reason = None
                translated = text.strip()
        except Exception:
            status = "failed"
            reason = "translation_unavailable"
            translated = None

        result = TranslationResult(
            paper_id=paper_id,
            original_abstract=original_abstract,
            translated_abstract=translated,
            status=status,
            source_abstract_sha256=source_hash,
            target_language=target_language,
            pipeline_version=self.pipeline_version,
            fallback_reason=reason,
        )
        self._cache[key] = result
        return result
