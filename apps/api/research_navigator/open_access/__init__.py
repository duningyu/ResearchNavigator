"""Lawful open-access resolution and ingestion helpers."""

from __future__ import annotations

from research_navigator.config import Settings
from research_navigator.db import Database
from research_navigator.open_access.arxiv import ArxivOpenAccessClient
from research_navigator.open_access.base import OpenAccessClient
from research_navigator.open_access.fetcher import SafePdfFetcher
from research_navigator.open_access.openalex import OpenAlexOpenAccessClient
from research_navigator.open_access.resolver import OpenAccessResolver
from research_navigator.open_access.semantic_scholar import SemanticScholarOpenAccessClient
from research_navigator.open_access.unpaywall import UnpaywallOpenAccessClient
from research_navigator.scholarly.coordinator import ArxivRequestCoordinator


def build_open_access_resolver(
    settings: Settings,
    *,
    database: Database | None = None,
    arxiv_coordinator: ArxivRequestCoordinator | None = None,
) -> OpenAccessResolver:
    """Build only public-source clients that are enabled/configured.

    Unpaywall is included only when the required contact email exists. No
    credential or contact value is exposed through the returned contracts.
    """

    clients: list[OpenAccessClient] = []
    if settings.enable_openalex:
        clients.append(
            OpenAlexOpenAccessClient(
                api_key=settings.openalex_api_key,
                mailto=settings.crossref_mailto,
            )
        )
    if settings.unpaywall_email:
        clients.append(UnpaywallOpenAccessClient(email=settings.unpaywall_email))
    if settings.enable_arxiv:
        coordinator = arxiv_coordinator
        if coordinator is None and database is not None:
            coordinator = ArxivRequestCoordinator(database=database)
        clients.append(ArxivOpenAccessClient(coordinator=coordinator))
    if settings.enable_semantic_scholar:
        clients.append(
            SemanticScholarOpenAccessClient(api_key=settings.semantic_scholar_api_key)
        )
    return OpenAccessResolver(clients)


def build_pdf_fetcher(settings: Settings) -> SafePdfFetcher:
    return SafePdfFetcher(max_bytes=settings.max_pdf_bytes)


__all__ = ["build_open_access_resolver", "build_pdf_fetcher"]
