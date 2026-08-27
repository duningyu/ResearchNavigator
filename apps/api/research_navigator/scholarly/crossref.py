"""Crossref REST works adapter."""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

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


def _first_date(item: dict[str, Any]) -> date | None:
    for key in ("published-print", "published-online", "issued"):
        parts = ((item.get(key) or {}).get("date-parts") or [[]])[0]
        if parts:
            year, month, day = (parts + [1, 1])[:3]
            try:
                return date(int(year), int(month), int(day))
            except (TypeError, ValueError, OverflowError):
                continue
    return None


class CrossrefAdapter(ScholarlyAdapter):
    name = "crossref"
    supports_evidence_acquisition = True
    base_url = "https://api.crossref.org/works"

    def __init__(self, *, mailto: str | None = None, timeout: float = 20.0) -> None:
        self.mailto = mailto
        self.timeout = timeout

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        params: dict[str, Any] = {
            "query.bibliographic": request.query,
            "rows": request.limit,
            "offset": request.offset,
        }
        filters: list[str] = []
        if request.year_from:
            filters.append(f"from-pub-date:{request.year_from}-01-01")
        if request.year_to:
            filters.append(f"until-pub-date:{request.year_to}-12-31")
        if filters:
            params["filter"] = ",".join(filters)
        if self.mailto:
            params["mailto"] = self.mailto
        headers = {"User-Agent": "ResearchNavigator/0.2 (mailto:local-research@example.invalid)"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
                response = await client.get(self.base_url, params=params)
                if response.status_code == 429:
                    return AdapterSearchResult(
                        status=SourceStatus(status="rate_limited", detail="Crossref returned 429")
                    )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return AdapterSearchResult(
                status=SourceStatus(status="error", detail=f"{type(exc).__name__}: {exc}")
            )

        records: list[PaperRecord] = []
        for item in (payload.get("message") or {}).get("items", []):
            title = " ".join(item.get("title") or []) or "Untitled"
            publication_date = _first_date(item)
            source_id = str(item.get("DOI") or item.get("URL") or title)
            raw_hash = hashlib.sha256(repr(sorted(item.items())).encode("utf-8")).hexdigest()
            abstract = item.get("abstract")
            provenance = SourceProvenance(
                source=self.name,
                source_id=source_id,
                source_url=item.get("URL"),
                raw_hash=raw_hash,
                is_fixture=False,
            )
            records.append(
                PaperRecord(
                    title=title,
                    abstract=abstract,
                    publication_year=publication_date.year if publication_date else None,
                    publication_date=publication_date,
                    authors=[
                        PaperAuthor(
                            name=" ".join(
                                part for part in [author.get("given"), author.get("family")] if part
                            )
                            or "Unknown",
                            orcid=author.get("ORCID"),
                            affiliations=[
                                affiliation.get("name", "")
                                for affiliation in author.get("affiliation", [])
                                if affiliation.get("name")
                            ],
                        )
                        for author in item.get("author", [])
                    ],
                    venue="; ".join(item.get("container-title") or []) or None,
                    venue_type=item.get("type"),
                    doi=item.get("DOI"),
                    external_ids={"crossref": source_id},
                    source_urls=[url for url in [item.get("URL")] if url],
                    publisher_url=item.get("URL"),
                    citation_count=item.get("is-referenced-by-count"),
                    reference_count=item.get("reference-count"),
                    source_provenance=[provenance],
                    abstract_provenance=provenance if abstract else None,
                    source_score=item.get("score"),
                )
            )
        return AdapterSearchResult(
            records=records, status=SourceStatus(status="ok", result_count=len(records))
        )
