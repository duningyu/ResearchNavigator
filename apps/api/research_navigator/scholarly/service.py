"""Federated search orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from research_navigator.config import Settings
from research_navigator.db import Database
from research_navigator.scholarly.arxiv import ArxivAdapter
from research_navigator.scholarly.base import (
    AdapterSearchResult,
    PaperRecord,
    ScholarlyAdapter,
    SearchRequest,
    SourceStatus,
)
from research_navigator.scholarly.coordinator import ArxivRequestCoordinator
from research_navigator.scholarly.crossref import CrossrefAdapter
from research_navigator.scholarly.fixture import FixtureAdapter
from research_navigator.scholarly.normalize import deduplicate_records
from research_navigator.scholarly.openalex import OpenAlexAdapter
from research_navigator.scholarly.query_adaptation import (
    ControlledGlossaryQueryAdapter,
    QueryAdaptationProvider,
    QueryAdaptationResult,
    resolve_query_adaptation,
)
from research_navigator.scholarly.semantic_scholar import SemanticScholarAdapter


@dataclass(slots=True)
class FederatedSearchResult:
    papers: list[PaperRecord]
    source_status: dict[str, SourceStatus]


class FederatedSearchService:
    def __init__(
        self,
        adapters: list[ScholarlyAdapter],
        *,
        query_adaptation_provider: QueryAdaptationProvider | None = None,
        query_adaptation_timeout_seconds: float = 0.5,
    ) -> None:
        self.adapters = {adapter.name: adapter for adapter in adapters}
        self.query_adaptation_provider = (
            query_adaptation_provider or ControlledGlossaryQueryAdapter()
        )
        self.query_adaptation_timeout_seconds = query_adaptation_timeout_seconds

    async def _resolve_source_query(
        self, request: SearchRequest, source: str
    ) -> QueryAdaptationResult:
        if source in request.source_queries:
            user_query = request.source_queries[source]
            return QueryAdaptationResult(
                original_query=user_query,
                adapted_query=None,
                status="ADAPTED",
                source="user_edited",
                used_fallback=False,
            )
        if not request.adapt_query:
            return QueryAdaptationResult(
                original_query=request.query,
                adapted_query=None,
                status="NOT_REQUIRED",
                source="original",
                used_fallback=False,
            )
        return await resolve_query_adaptation(
            request.query,
            source,
            self.query_adaptation_provider,
            self.query_adaptation_timeout_seconds,
        )

    async def _search_adapter(
        self, adapter: ScholarlyAdapter, request: SearchRequest
    ) -> tuple[QueryAdaptationResult, list[AdapterSearchResult], list[Exception]]:
        adaptation = await self._resolve_source_query(request, adapter.name)
        responses: list[AdapterSearchResult] = []
        errors: list[Exception] = []
        for query in adaptation.executed_queries:
            try:
                responses.append(await adapter.search(request.model_copy(update={"query": query})))
            except Exception as error:
                errors.append(error)
        return adaptation, responses, errors

    async def search(
        self, request: SearchRequest, *, selected_names: list[str] | None = None
    ) -> FederatedSearchResult:
        selected_names = (
            selected_names
            if selected_names is not None
            else (request.sources or list(self.adapters))
        )
        selected = [self.adapters[name] for name in selected_names if name in self.adapters]
        unknown = [name for name in selected_names if name not in self.adapters]
        tasks = [self._search_adapter(adapter, request) for adapter in selected]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        records: list[PaperRecord] = []
        statuses: dict[str, SourceStatus] = {
            name: SourceStatus(status="disabled", detail="Source is not enabled")
            for name in unknown
        }
        for adapter, result in zip(selected, results, strict=True):
            if isinstance(result, BaseException):
                statuses[adapter.name] = SourceStatus(
                    status="error", detail=f"{type(result).__name__}: {result}"
                )
                continue
            adaptation, responses, errors = result
            if not responses:
                error = errors[-1] if errors else RuntimeError("Source search failed")
                statuses[adapter.name] = SourceStatus(
                    status="error", detail=f"{type(error).__name__}: {error}"
                )
                continue
            last_response = responses[-1]
            response_metadata: dict[str, object] = {}
            for response in responses:
                response_metadata.update(response.status.metadata)
            metadata: dict[str, object] = {
                **response_metadata,
                "original_query": request.query,
                "executed_query": adaptation.executed_query,
                "executed_queries": list(adaptation.executed_queries),
                "query_adaptation": (
                    "controlled_glossary"
                    if adaptation.status == "ADAPTED" and adaptation.source == "controlled_glossary"
                    else "user_edited"
                    if adaptation.status == "ADAPTED" and adaptation.source == "user_edited"
                    else "fallback_original"
                    if adaptation.status == "FALLBACK_ORIGINAL"
                    else "original"
                ),
                "query_adaptation_status": adaptation.status,
                "query_adaptation_source": adaptation.source,
                "query_adaptation_used_fallback": adaptation.used_fallback,
                "query_adaptation_version": "rn-ux-r1-glossary-v2",
            }
            if adaptation.failure_reason is not None:
                metadata["query_adaptation_failure"] = adaptation.failure_reason
            statuses[adapter.name] = last_response.status.model_copy(
                update={
                    "result_count": sum(response.status.result_count for response in responses),
                    "metadata": metadata,
                }
            )
            for response in responses:
                records.extend(response.records)
        deduplicated = deduplicate_records(records)
        deduplicated.sort(key=lambda item: item.source_score or 0.0, reverse=True)
        return FederatedSearchResult(papers=deduplicated[: request.limit], source_status=statuses)

    async def resolve_exact(
        self, doi: str, *, selected_names: list[str] | None = None
    ) -> PaperRecord | None:
        names = selected_names if selected_names is not None else list(self.adapters)
        for name in names:
            adapter = self.adapters.get(name)
            if adapter is None:
                continue
            try:
                record = await adapter.resolve_exact(doi)
            except Exception:
                continue
            if record is not None:
                return record
        return None


def build_search_service(
    settings: Settings,
    *,
    database: Database | None = None,
    arxiv_coordinator: ArxivRequestCoordinator | None = None,
) -> FederatedSearchService:
    adapters: list[ScholarlyAdapter] = []
    if settings.enable_fixture_source:
        adapters.append(FixtureAdapter())
    if settings.enable_openalex:
        adapters.append(
            OpenAlexAdapter(
                mailto=settings.crossref_mailto,
                api_key=settings.openalex_api_key,
            )
        )
    if settings.enable_crossref:
        adapters.append(CrossrefAdapter(mailto=settings.crossref_mailto))
    if settings.enable_arxiv:
        coordinator = arxiv_coordinator
        if coordinator is None and database is not None:
            coordinator = ArxivRequestCoordinator(database=database)
        adapters.append(ArxivAdapter(coordinator=coordinator))
    if settings.enable_semantic_scholar:
        adapters.append(SemanticScholarAdapter(api_key=settings.semantic_scholar_api_key))
    return FederatedSearchService(adapters)
