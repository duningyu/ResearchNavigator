"""OpenAlex works adapter."""

from __future__ import annotations

import hashlib
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


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rate_limit_metadata(response: httpx.Response) -> dict[str, object]:
    metadata: dict[str, object] = {"http_status": response.status_code}
    limit = _safe_int(response.headers.get("X-RateLimit-Limit"))
    remaining = _safe_int(response.headers.get("X-RateLimit-Remaining"))
    retry_after = _safe_int(response.headers.get("Retry-After"))
    reset = response.headers.get("X-RateLimit-Reset")
    if limit is not None:
        metadata["rate_limit_limit"] = limit
    if remaining is not None:
        metadata["rate_limit_remaining"] = remaining
    if reset:
        metadata["rate_limit_reset"] = reset
    if retry_after is not None:
        metadata["retry_after_seconds"] = retry_after
    return metadata

def _abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    positions = [(position, word) for word, values in index.items() for position in values]
    return " ".join(word for _, word in sorted(positions))


class OpenAlexAdapter(ScholarlyAdapter):
    name = "openalex"
    supports_evidence_acquisition = True
    base_url = "https://api.openalex.org/works"

    def __init__(
        self,
        *,
        mailto: str | None = None,
        api_key: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.mailto = mailto
        self.api_key = api_key
        self.timeout = timeout

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        params: dict[str, Any] = {
            "search": request.query,
            "per-page": request.limit,
            "page": request.offset // request.limit + 1,
        }
        filters: list[str] = []
        if request.year_from:
            filters.append(f"from_publication_date:{request.year_from}-01-01")
        if request.year_to:
            filters.append(f"to_publication_date:{request.year_to}-12-31")
        if request.open_access_only:
            filters.append("is_oa:true")
        if filters:
            params["filter"] = ",".join(filters)
        if self.mailto:
            params["mailto"] = self.mailto
        if self.api_key:
            params["api_key"] = self.api_key
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.base_url, params=params)
                metadata = _rate_limit_metadata(response)
                if response.status_code == 429:
                    return AdapterSearchResult(
                        status=SourceStatus(
                            status="rate_limited",
                            detail="OpenAlex returned 429",
                            metadata=metadata,
                        )
                    )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return AdapterSearchResult(
                status=SourceStatus(status="error", detail=f"{type(exc).__name__}: {exc}")
            )

        records: list[PaperRecord] = []
        for item in payload.get("results", []):
            ids = item.get("ids") or {}
            authors = [
                PaperAuthor(
                    name=(authorship.get("author") or {}).get("display_name") or "Unknown",
                    orcid=(authorship.get("author") or {}).get("orcid"),
                    affiliations=[
                        institution.get("display_name", "")
                        for institution in authorship.get("institutions", [])
                        if institution.get("display_name")
                    ],
                    source_author_id=(authorship.get("author") or {}).get("id"),
                )
                for authorship in item.get("authorships", [])
            ]
            source = (item.get("primary_location") or {}).get("source") or {}
            primary = item.get("primary_location") or {}
            source_id = str(item.get("id") or ids.get("openalex") or "")
            raw_hash = hashlib.sha256(
                repr(sorted(item.items(), key=lambda pair: pair[0])).encode("utf-8")
            ).hexdigest()
            abstract = _abstract_from_inverted_index(item.get("abstract_inverted_index"))
            provenance = SourceProvenance(
                source=self.name,
                source_id=source_id,
                source_url=item.get("id"),
                raw_hash=raw_hash,
                is_fixture=False,
            )
            records.append(
                PaperRecord(
                    title=item.get("display_name") or item.get("title") or "Untitled",
                    abstract=abstract,
                    publication_year=item.get("publication_year"),
                    authors=authors,
                    venue=source.get("display_name"),
                    venue_type=source.get("type"),
                    doi=ids.get("doi"),
                    external_ids={k: str(v) for k, v in ids.items() if v},
                    source_urls=[
                        url for url in [item.get("id"), primary.get("landing_page_url")] if url
                    ],
                    publisher_url=primary.get("landing_page_url"),
                    pdf_url=primary.get("pdf_url"),
                    open_access_status=(item.get("open_access") or {}).get("oa_status"),
                    citation_count=item.get("cited_by_count"),
                    concepts=[
                        concept.get("display_name", "")
                        for concept in item.get("concepts", [])[:10]
                        if concept.get("display_name")
                    ],
                    source_provenance=[provenance],
                    abstract_provenance=provenance if abstract else None,
                    source_score=item.get("relevance_score"),
                )
            )
        return AdapterSearchResult(
            records=records,
            status=SourceStatus(
                status="ok", result_count=len(records), metadata=metadata
            ),
        )
