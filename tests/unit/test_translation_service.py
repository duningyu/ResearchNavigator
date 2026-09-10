from __future__ import annotations

from dataclasses import dataclass

from research_navigator.translation.service import TranslationService


@dataclass
class StubAdapter:
    text: str = "这是忠实译文。"
    complete: bool = True
    calls: int = 0

    def translate(self, text: str, target_language: str):
        self.calls += 1
        return {"text": self.text, "complete": self.complete}


@dataclass
class FailingAdapter:
    calls: int = 0

    def translate(self, text: str, target_language: str):
        self.calls += 1
        raise TimeoutError("translation stub timeout")


def test_translation_preserves_original_and_hits_content_identity_cache() -> None:
    adapter = StubAdapter()
    service = TranslationService(adapter=adapter, pipeline_version="stub-v1")

    first = service.translate(7, "The model reaches 95% accuracy on ImageNet.", "zh-CN")
    second = service.translate(7, "The model reaches 95% accuracy on ImageNet.", "zh-CN")

    assert first.status == "ready"
    assert first.original_abstract == "The model reaches 95% accuracy on ImageNet."
    assert first.translated_abstract == "这是忠实译文。"
    assert first.source_abstract_sha256
    assert second.cache_hit is True
    assert adapter.calls == 1


def test_abstract_change_invalidates_translation_cache() -> None:
    adapter = StubAdapter()
    service = TranslationService(adapter=adapter, pipeline_version="stub-v1")

    service.translate(7, "Version one.", "zh-CN")
    result = service.translate(7, "Version two.", "zh-CN")

    assert result.status == "ready"
    assert result.cache_hit is False
    assert adapter.calls == 2


def test_translation_cache_is_scoped_by_language_and_pipeline_version() -> None:
    adapter = StubAdapter()
    service = TranslationService(adapter=adapter, pipeline_version="stub-v1")

    service.translate(7, "Same abstract.", "zh-CN")
    service.translate(7, "Same abstract.", "en")
    other_pipeline = TranslationService(adapter=adapter, pipeline_version="stub-v2")
    other_pipeline.translate(7, "Same abstract.", "zh-CN")

    assert adapter.calls == 3


def test_translation_adapter_failure_preserves_original_abstract() -> None:
    adapter = FailingAdapter()
    result = TranslationService(adapter=adapter).translate(
        1, "Original abstract.", "zh-CN"
    )

    assert result.status == "failed"
    assert result.fallback_reason == "translation_unavailable"
    assert result.original_abstract == "Original abstract."
    assert result.translated_abstract is None


def test_empty_or_partial_translation_falls_back_without_overwriting_original() -> None:
    empty = TranslationService(adapter=StubAdapter(text=""))
    partial = TranslationService(adapter=StubAdapter(text="不完整", complete=False))

    empty_result = empty.translate(1, "Original abstract.", "zh-CN")
    partial_result = partial.translate(1, "Original abstract.", "zh-CN")

    assert empty_result.status == "failed"
    assert empty_result.translated_abstract is None
    assert empty_result.original_abstract == "Original abstract."
    assert partial_result.status == "partial"
    assert partial_result.translated_abstract is None


def test_missing_original_abstract_is_unavailable() -> None:
    result = TranslationService(adapter=StubAdapter()).translate(1, None, "zh-CN")

    assert result.status == "unavailable"
    assert result.translated_abstract is None
