"""Federated search orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from research_navigator.config import Settings
from research_navigator.scholarly.arxiv import ArxivAdapter
from research_navigator.scholarly.base import (
    PaperRecord,
    ScholarlyAdapter,
    SearchRequest,
    SourceStatus,
)
from research_navigator.scholarly.crossref import CrossrefAdapter
from research_navigator.scholarly.fixture import FixtureAdapter
from research_navigator.scholarly.normalize import deduplicate_records
from research_navigator.scholarly.openalex import OpenAlexAdapter
from research_navigator.scholarly.semantic_scholar import SemanticScholarAdapter


@dataclass(slots=True)
class FederatedSearchResult:
    papers: list[PaperRecord]
    source_status: dict[str, SourceStatus]


class FederatedSearchService:
    def __init__(self, adapters: list[ScholarlyAdapter]) -> None:
        self.adapters = {adapter.name: adapter for adapter in adapters}

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
        tasks = [adapter.search(request) for adapter in selected]
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
            statuses[adapter.name] = result.status
            records.extend(result.records)
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


def build_search_service(settings: Settings) -> FederatedSearchService:
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
        adapters.append(ArxivAdapter())
    if settings.enable_semantic_scholar:
        adapters.append(SemanticScholarAdapter(api_key=settings.semantic_scholar_api_key))
    return FederatedSearchService(adapters)
