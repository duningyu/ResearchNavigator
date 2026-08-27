"""Semantic Scholar Academic Graph adapter."""

from __future__ import annotations

import hashlib

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


class SemanticScholarAdapter(ScholarlyAdapter):
    name = "semantic_scholar"
    supports_evidence_acquisition = True
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(self, *, api_key: str | None = None, timeout: float = 20.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        params: dict[str, str | int] = {
            "query": request.query,
            "limit": request.limit,
            "offset": request.offset,
            "fields": (
                "paperId,title,abstract,year,authors,venue,publicationTypes,externalIds,url,"
                "openAccessPdf,citationCount,referenceCount,fieldsOfStudy"
            ),
        }
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
                response = await client.get(self.base_url, params=params)
                if response.status_code == 429:
                    return AdapterSearchResult(
                        status=SourceStatus(
                            status="rate_limited", detail="Semantic Scholar returned 429"
                        )
                    )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return AdapterSearchResult(
                status=SourceStatus(status="error", detail=f"{type(exc).__name__}: {exc}")
            )

        records: list[PaperRecord] = []
        for item in payload.get("data", []):
            external_ids = item.get("externalIds") or {}
            source_id = item.get("paperId") or ""
            oa_pdf = item.get("openAccessPdf") or {}
            raw_hash = hashlib.sha256(repr(sorted(item.items())).encode("utf-8")).hexdigest()
            abstract = item.get("abstract")
            provenance = SourceProvenance(
                source=self.name,
                source_id=source_id,
                source_url=item.get("url"),
                raw_hash=raw_hash,
                is_fixture=False,
            )
            records.append(
                PaperRecord(
                    title=item.get("title") or "Untitled",
                    abstract=abstract,
                    publication_year=item.get("year"),
                    authors=[
                        PaperAuthor(
                            name=author.get("name") or "Unknown",
                            source_author_id=author.get("authorId"),
                        )
                        for author in item.get("authors", [])
                    ],
                    venue=item.get("venue") or None,
                    venue_type=", ".join(item.get("publicationTypes") or []) or None,
                    doi=external_ids.get("DOI"),
                    arxiv_id=external_ids.get("ArXiv"),
                    external_ids={k: str(v) for k, v in external_ids.items() if v},
                    source_urls=[url for url in [item.get("url")] if url],
                    publisher_url=item.get("url"),
                    pdf_url=oa_pdf.get("url"),
                    open_access_status="open" if oa_pdf.get("url") else None,
                    citation_count=item.get("citationCount"),
                    reference_count=item.get("referenceCount"),
                    fields_of_study=item.get("fieldsOfStudy") or [],
                    source_provenance=[provenance],
                    abstract_provenance=provenance if abstract else None,
                )
            )
        return AdapterSearchResult(
            records=records, status=SourceStatus(status="ok", result_count=len(records))
        )
