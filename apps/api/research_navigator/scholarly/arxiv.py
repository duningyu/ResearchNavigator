"""arXiv Atom API adapter."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from contextlib import suppress
from datetime import date

import httpx

from research_navigator.scholarly.base import (
    AdapterSearchResult,
    PaperAuthor,
    PaperRecord,
    ScholarlyAdapter,
    SearchRequest,
    SourceProvenance,
    SourceStatus,
)
from research_navigator.scholarly.coordinator import (
    ArxivRequestCoordinator,
    CoordinatorUnavailable,
)

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"


class ArxivAdapter(ScholarlyAdapter):
    name = "arxiv"
    supports_evidence_acquisition = True
    base_url = "https://export.arxiv.org/api/query"

    def __init__(
        self,
        *,
        timeout: float = 25.0,
        coordinator: ArxivRequestCoordinator | None = None,
    ) -> None:
        self.timeout = timeout
        self.coordinator = coordinator

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        params: dict[str, str | int] = {
            "search_query": f"all:{request.query}",
            "start": request.offset,
            "max_results": request.limit,
            "sortBy": "relevance",
        }
        async def fetch() -> bytes:
            async with httpx.AsyncClient(
                timeout=self.timeout, headers={"User-Agent": "ResearchNavigator/0.2"}
            ) as client:
                response = await client.get(self.base_url, params=params)
                if response.status_code == 429:
                    raise httpx.HTTPStatusError(
                        "arXiv returned 429", request=response.request, response=response
                    )
                response.raise_for_status()
                return response.content

        try:
            content = (
                await self.coordinator.run("search", fetch)
                if self.coordinator is not None
                else await fetch()
            )
            root = ET.fromstring(content)
        except CoordinatorUnavailable as exc:
            return AdapterSearchResult(
                status=SourceStatus(status="error", detail=f"CoordinatorUnavailable: {exc}")
            )
        except Exception as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                return AdapterSearchResult(
                    status=SourceStatus(status="rate_limited", detail="arXiv returned 429")
                )
            return AdapterSearchResult(
                status=SourceStatus(status="error", detail=f"{type(exc).__name__}: {exc}")
            )

        records: list[PaperRecord] = []
        for entry in root.findall(f"{_ATOM}entry"):
            entry_id = (entry.findtext(f"{_ATOM}id") or "").strip()
            arxiv_id = entry_id.rsplit("/", 1)[-1]
            published = (entry.findtext(f"{_ATOM}published") or "")[:10]
            publication_date = None
            with suppress(ValueError):
                publication_date = date.fromisoformat(published)
            if request.year_from and publication_date and publication_date.year < request.year_from:
                continue
            if request.year_to and publication_date and publication_date.year > request.year_to:
                continue
            links = {
                link.attrib.get("rel", "alternate"): link.attrib.get("href", "")
                for link in entry.findall(f"{_ATOM}link")
            }
            pdf_url = next(
                (
                    link.attrib.get("href")
                    for link in entry.findall(f"{_ATOM}link")
                    if link.attrib.get("title") == "pdf"
                ),
                None,
            )
            license_text = (entry.findtext(f"{_ARXIV}license") or "").strip() or None
            doi = entry.findtext(f"{_ARXIV}doi")
            raw_hash = hashlib.sha256(ET.tostring(entry)).hexdigest()
            abstract = " ".join((entry.findtext(f"{_ATOM}summary") or "").split()) or None
            provenance = SourceProvenance(
                source=self.name,
                source_id=arxiv_id,
                source_url=entry_id,
                raw_hash=raw_hash,
                is_fixture=False,
            )
            records.append(
                PaperRecord(
                    title=" ".join((entry.findtext(f"{_ATOM}title") or "Untitled").split()),
                    abstract=abstract,
                    publication_year=publication_date.year if publication_date else None,
                    publication_date=publication_date,
                    authors=[
                        PaperAuthor(name=author.findtext(f"{_ATOM}name") or "Unknown")
                        for author in entry.findall(f"{_ATOM}author")
                    ],
                    venue=entry.findtext(f"{_ARXIV}journal_ref"),
                    venue_type="preprint",
                    doi=doi,
                    arxiv_id=arxiv_id,
                    external_ids={"arxiv": arxiv_id},
                    source_urls=[url for url in [entry_id, links.get("alternate")] if url],
                    publisher_url=links.get("alternate") or entry_id,
                    pdf_url=pdf_url,
                    open_access_status="green",
                    license=license_text,
                    keywords=[
                        category.attrib.get("term", "")
                        for category in entry.findall(f"{_ATOM}category")
                        if category.attrib.get("term")
                    ],
                    source_provenance=[provenance],
                    abstract_provenance=provenance if abstract else None,
                )
            )
        return AdapterSearchResult(
            records=records, status=SourceStatus(status="ok", result_count=len(records))
        )
