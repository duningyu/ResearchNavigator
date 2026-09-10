import asyncio

import pytest

from research_navigator.scholarly.base import (
    AdapterSearchResult,
    PaperRecord,
    ScholarlyAdapter,
    SearchRequest,
    SourceStatus,
)
from research_navigator.scholarly.service import FederatedSearchService


class RecordingSource(ScholarlyAdapter):
    def __init__(
        self,
        name: str,
        records_by_query: dict[str, list[PaperRecord]] | None = None,
    ) -> None:
        self.name = name
        self.requests: list[SearchRequest] = []
        self.records_by_query = records_by_query or {}

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        self.requests.append(request)
        records = self.records_by_query.get(request.query, [])
        return AdapterSearchResult(
            records=records,
            status=SourceStatus(status="ok", result_count=len(records)),
        )


class StaticAdaptationProvider:
    def __init__(self, value: str | None) -> None:
        self.value = value
        self.calls: list[tuple[str, str]] = []

    async def adapt(self, query: str, source: str) -> str | None:
        self.calls.append((query, source))
        return self.value


class ErrorAdaptationProvider:
    async def adapt(self, query: str, source: str) -> str | None:
        raise RuntimeError("provider failure")


class TimeoutAdaptationProvider:
    async def adapt(self, query: str, source: str) -> str | None:
        await asyncio.sleep(1)
        return "never returned"


@pytest.mark.asyncio
async def test_source_query_adaptation_preserves_original_and_does_not_invent_domain():
    arxiv = RecordingSource("arxiv")
    fixture = RecordingSource("fixture")
    request = SearchRequest(query="图像语义分割", limit=7, year_from=2020)
    result = await FederatedSearchService([arxiv, fixture]).search(request)
    assert [item.query for item in arxiv.requests] == [
        "图像语义分割",
        "image semantic segmentation",
    ]
    assert arxiv.requests[0].limit == 7
    assert arxiv.requests[0].year_from == 2020
    assert fixture.requests[0].query == request.query == "图像语义分割"
    metadata = result.source_status["arxiv"].metadata
    assert metadata["original_query"] == "图像语义分割"
    assert metadata["executed_query"] == "image semantic segmentation"
    assert metadata["executed_queries"] == [
        "图像语义分割",
        "image semantic segmentation",
    ]
    assert metadata["query_adaptation_status"] == "ADAPTED"
    assert metadata["query_adaptation_source"] == "controlled_glossary"
    assert metadata["query_adaptation_used_fallback"] is False
    assert "industrial" not in metadata["executed_query"]
    assert "warning" not in metadata["executed_query"]


@pytest.mark.asyncio
async def test_unknown_chinese_is_preserved_and_not_falsely_claimed_translated():
    adapter = RecordingSource("arxiv")
    result = await FederatedSearchService([adapter]).search(SearchRequest(query="甲乙新术语"))
    assert adapter.requests[0].query == "甲乙新术语"
    assert result.source_status["arxiv"].metadata["query_adaptation_status"] == "FALLBACK_ORIGINAL"
    assert result.source_status["arxiv"].metadata["query_adaptation_used_fallback"] is True


@pytest.mark.asyncio
async def test_english_bibliographic_query_is_not_rewritten():
    adapter = RecordingSource("arxiv")
    query = '"Attention Is All You Need"'
    result = await FederatedSearchService([adapter]).search(SearchRequest(query=query))
    assert adapter.requests[0].query == query
    assert result.source_status["arxiv"].metadata["query_adaptation_status"] == "NOT_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query", ['"深度学习中的未来窗口预警"', 'ti:"图像语义分割"', "10.1234/深度学习"]
)
async def test_exact_bibliographic_or_source_syntax_is_preserved(query: str):
    adapter = RecordingSource("arxiv")
    await FederatedSearchService([adapter]).search(SearchRequest(query=query))
    assert adapter.requests[0].query == query


@pytest.mark.asyncio
async def test_future_window_warning_remains_a_future_prediction_task():
    adapter = RecordingSource("arxiv")
    await FederatedSearchService([adapter]).search(SearchRequest(query="未来窗口预警"))
    assert [item.query for item in adapter.requests] == ["未来窗口预警", "future window early warning"]
    assert all("detection" not in item.query for item in adapter.requests)


@pytest.mark.asyncio
async def test_explicit_source_query_overrides_only_its_source_and_keeps_original():
    arxiv, crossref = RecordingSource("arxiv"), RecordingSource("crossref")
    request = SearchRequest.model_validate({
        "query": "图像语义分割", "source_queries": {"arxiv": 'ti:"semantic segmentation"'}
    })
    result = await FederatedSearchService([arxiv, crossref]).search(request)
    assert arxiv.requests[0].query == 'ti:"semantic segmentation"'
    assert [item.query for item in crossref.requests] == [
        "图像语义分割",
        "image semantic segmentation",
    ]
    assert request.query == "图像语义分割"
    assert result.source_status["arxiv"].metadata["query_adaptation_status"] == "ADAPTED"
    assert result.source_status["arxiv"].metadata["query_adaptation_source"] == "user_edited"


@pytest.mark.asyncio
async def test_user_can_disable_automatic_adaptation():
    adapter = RecordingSource("arxiv")
    request = SearchRequest.model_validate({"query": "图像语义分割", "adapt_query": False})
    await FederatedSearchService([adapter]).search(request)
    assert adapter.requests[0].query == "图像语义分割"


@pytest.mark.asyncio
async def test_query_adaptation_timeout_falls_back_to_original_query():
    adapter = RecordingSource("arxiv")
    provider = TimeoutAdaptationProvider()
    result = await FederatedSearchService(
        [adapter],
        query_adaptation_provider=provider,
        query_adaptation_timeout_seconds=0.01,
    ).search(SearchRequest(query="未来窗口预警"))
    assert [item.query for item in adapter.requests] == ["未来窗口预警"]
    metadata = result.source_status["arxiv"].metadata
    assert metadata["query_adaptation_status"] == "FALLBACK_ORIGINAL"
    assert metadata["query_adaptation_used_fallback"] is True
    assert metadata["executed_queries"] == ["未来窗口预警"]


@pytest.mark.asyncio
async def test_query_adaptation_error_falls_back_to_original_query():
    adapter = RecordingSource("arxiv")
    result = await FederatedSearchService(
        [adapter], query_adaptation_provider=ErrorAdaptationProvider()
    ).search(SearchRequest(query="未来窗口预警"))
    assert [item.query for item in adapter.requests] == ["未来窗口预警"]
    assert result.source_status["arxiv"].metadata["query_adaptation_status"] == "FALLBACK_ORIGINAL"


@pytest.mark.asyncio
async def test_empty_query_adaptation_is_not_success():
    adapter = RecordingSource("arxiv")
    result = await FederatedSearchService(
        [adapter], query_adaptation_provider=StaticAdaptationProvider("   ")
    ).search(SearchRequest(query="未来窗口预警"))
    assert [item.query for item in adapter.requests] == ["未来窗口预警"]
    assert result.source_status["arxiv"].metadata["query_adaptation_status"] == "FALLBACK_ORIGINAL"


@pytest.mark.asyncio
async def test_fallback_preserves_future_window_intent_without_generic_expansion():
    adapter = RecordingSource("arxiv")
    result = await FederatedSearchService(
        [adapter], query_adaptation_provider=ErrorAdaptationProvider()
    ).search(SearchRequest(query="未来窗口早期预警"))
    assert adapter.requests[0].query == "未来窗口早期预警"
    assert "异常检测" not in adapter.requests[0].query
    assert "机器学习" not in adapter.requests[0].query
    assert result.source_status["arxiv"].metadata["original_query"] == "未来窗口早期预警"


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["10.1234/未来窗口预警", 'ti:"未来窗口预警"'])
async def test_precise_queries_bypass_adaptation_provider(query: str):
    adapter = RecordingSource("arxiv")
    provider = StaticAdaptationProvider("must not be used")
    result = await FederatedSearchService(
        [adapter], query_adaptation_provider=provider
    ).search(SearchRequest(query=query))
    assert [item.query for item in adapter.requests] == [query]
    assert provider.calls == []
    assert result.source_status["arxiv"].metadata["query_adaptation_status"] == "NOT_REQUIRED"


@pytest.mark.asyncio
async def test_successful_adaptation_queries_both_variants_and_deduplicates_records():
    paper = PaperRecord(title="Same paper", doi="10.1234/same")
    adapter = RecordingSource(
        "arxiv",
        records_by_query={
            "未来窗口预警": [paper],
            "future window early warning": [paper],
        },
    )
    provider = StaticAdaptationProvider("future window early warning")
    result = await FederatedSearchService(
        [adapter], query_adaptation_provider=provider
    ).search(SearchRequest(query="未来窗口预警"))
    assert [item.query for item in adapter.requests] == [
        "未来窗口预警",
        "future window early warning",
    ]
    assert len(result.papers) == 1
    assert result.source_status["arxiv"].metadata["query_adaptation_status"] == "ADAPTED"


@pytest.mark.parametrize("queries", [{"unknown": "x"}, {"arxiv": " "}, {"arxiv": "x" * 501}])
def test_user_query_override_is_bounded(queries):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SearchRequest.model_validate({"query": "图像语义分割", "source_queries": queries})
