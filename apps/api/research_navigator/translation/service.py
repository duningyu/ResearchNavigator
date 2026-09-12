"""Abstract translation orchestration and provider boundary."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.config import Settings
from research_navigator.models import AbstractTranslationCache

TRANSLATION_PROMPT_VERSION = "abstract-translation-v1"


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
    """Adapter used when no approved translation provider is configured."""

    def translate(self, text: str, target_language: str) -> TranslationDraft:
        raise RuntimeError("translation adapter is not configured")


class OpenAICompatibleTranslationAdapter:
    """Minimal translation-only call through an OpenAI-compatible endpoint."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def translate(self, text: str, target_language: str) -> TranslationDraft:
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Translate the supplied academic abstract into the requested "
                            "language. Translate only. Preserve model names, dataset names, "
                            "formulas, variables, numbers, units, and negation. Do not "
                            "summarize, explain, add facts, or draw conclusions."
                        ),
                    },
                    {"role": "user", "content": f"Target language: {target_language}\n\n{text}"},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        try:
            translated = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("translation provider returned an invalid response") from exc
        if not isinstance(translated, str) or not translated.strip():
            raise RuntimeError("translation provider returned empty content")
        return TranslationDraft(translated.strip())


def build_translation_adapter(settings: Settings) -> TranslationAdapter:
    if settings.translation_provider != "openai_compatible":
        return UnavailableTranslationAdapter()
    if not settings.llm_base_url or not settings.llm_api_key:
        return UnavailableTranslationAdapter()
    model = settings.translation_model or settings.llm_model
    if not model:
        return UnavailableTranslationAdapter()
    return OpenAICompatibleTranslationAdapter(
        settings.llm_base_url, settings.llm_api_key, model,
        timeout=settings.llm_timeout_seconds,
    )


class TranslationService:
    def __init__(
        self,
        adapter: TranslationAdapter | None = None,
        *,
        pipeline_version: str = TRANSLATION_PROMPT_VERSION,
    ) -> None:
        self.adapter = adapter or UnavailableTranslationAdapter()
        self.pipeline_version = pipeline_version
        self._cache: dict[tuple[int, str, str, str], TranslationResult] = {}

    @staticmethod
    def _source_hash(original_abstract: str | None) -> str | None:
        if not original_abstract or not original_abstract.strip():
            return None
        return hashlib.sha256(original_abstract.encode("utf-8")).hexdigest()

    def _result(
        self,
        paper_id: int,
        original_abstract: str | None,
        target_language: str,
        status: str,
        source_hash: str | None,
        translated: str | None,
        reason: str | None,
        *,
        cache_hit: bool = False,
    ) -> TranslationResult:
        return TranslationResult(
            paper_id,
            original_abstract,
            translated,
            status,
            source_hash,
            target_language,
            self.pipeline_version,
            reason,
            cache_hit,
        )

    def lookup(
        self,
        paper_id: int,
        original_abstract: str | None,
        target_language: str,
        session: Session | None = None,
    ) -> TranslationResult:
        source_hash = self._source_hash(original_abstract)
        if source_hash is None:
            return self._result(
                paper_id,
                original_abstract,
                target_language,
                "unavailable",
                None,
                None,
                "original_abstract_unavailable",
            )
        assert original_abstract is not None
        key = (paper_id, source_hash, target_language, self.pipeline_version)
        if session is not None:
            row = session.scalar(
                select(AbstractTranslationCache).where(
                    AbstractTranslationCache.paper_id == paper_id,
                    AbstractTranslationCache.source_abstract_sha256 == source_hash,
                    AbstractTranslationCache.target_language == target_language,
                    AbstractTranslationCache.pipeline_version == self.pipeline_version,
                )
            )
            if row is not None and row.status == "ready":
                return self._result(
                    paper_id,
                    original_abstract,
                    target_language,
                    "ready",
                    source_hash,
                    row.translated_abstract,
                    None,
                    cache_hit=True,
                )
        cached = self._cache.get(key)
        if cached is not None and cached.status == "ready":
            return TranslationResult(**{**cached.__dict__, "cache_hit": True})
        return self._result(
            paper_id,
            original_abstract,
            target_language,
            "unavailable",
            source_hash,
            None,
            "translation_not_generated",
        )

    def translate(
        self,
        paper_id: int,
        original_abstract: str | None,
        target_language: str,
        session: Session | None = None,
    ) -> TranslationResult:
        source_hash = self._source_hash(original_abstract)
        if source_hash is None:
            return self._result(
                paper_id,
                original_abstract,
                target_language,
                "unavailable",
                None,
                None,
                "original_abstract_unavailable",
            )
        assert original_abstract is not None
        cached = self.lookup(paper_id, original_abstract, target_language, session)
        if cached.status == "ready":
            return cached
        try:
            draft = self.adapter.translate(original_abstract, target_language)
            text = draft.get("text") if isinstance(draft, dict) else draft.text
            complete = draft.get("complete", True) if isinstance(draft, dict) else draft.complete
            if not isinstance(text, str) or not text.strip():
                status, reason, translated = "failed", "empty_translation", None
            elif complete is False:
                status, reason, translated = "partial", "partial_translation", None
            else:
                status, reason, translated = "ready", None, text.strip()
        except Exception:
            status, reason, translated = "failed", "translation_unavailable", None
        result = self._result(
            paper_id,
            original_abstract,
            target_language,
            status,
            source_hash,
            translated,
            reason,
        )
        if status == "ready":
            self._cache[(paper_id, source_hash, target_language, self.pipeline_version)] = result
            if session is not None:
                session.add(
                    AbstractTranslationCache(
                        paper_id=paper_id,
                        source_abstract_sha256=source_hash,
                        target_language=target_language,
                        pipeline_version=self.pipeline_version,
                        translated_abstract=translated,
                        status="ready",
                        fallback_reason=None,
                    )
                )
                session.commit()
        return result
