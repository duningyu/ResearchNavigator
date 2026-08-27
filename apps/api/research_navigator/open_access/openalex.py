"""OpenAlex OA-location resolver."""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import quote

import httpx

from research_navigator.open_access.base import (
    OpenAccessCandidate,
    PaperIdentity,
    payload_hash,
)


class OpenAlexOpenAccessClient:
    name = "openalex"
    base_url = "https://api.openalex.org/works"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        mailto: str | None = None,
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.mailto = mailto
        self.timeout = timeout
        self.transport = transport

    async def resolve(self, identity: PaperIdentity) -> list[OpenAccessCandidate]:
        identifier: str | None = None
        if identity.doi:
            identifier = f"https://doi.org/{identity.doi.removeprefix('https://doi.org/')}"
        elif identity.arxiv_id:
            identifier = f"https://arxiv.org/abs/{identity.arxiv_id}"
        if identifier is None:
            return []
        params: dict[str, str] = {}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.mailto:
            params["mailto"] = self.mailto
        url = f"{self.base_url}/{quote(identifier, safe='')}"
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = cast(dict[str, Any], response.json())
        locations: list[dict[str, Any]] = []
        best = payload.get("best_oa_location")
        if isinstance(best, dict):
            locations.append(cast(dict[str, Any], best))
        for item in payload.get("locations") or []:
            if isinstance(item, dict) and item not in locations:
                locations.append(cast(dict[str, Any], item))
        open_access = payload.get("open_access") or {}
        is_oa = bool(open_access.get("is_oa")) if isinstance(open_access, dict) else False
        record_id = str(payload.get("id") or identifier)
        result: list[OpenAccessCandidate] = []
        for location in locations:
            source = location.get("source") or {}
            result.append(
                OpenAccessCandidate(
                    source=self.name,
                    source_record_id=record_id,
                    landing_url=location.get("landing_page_url"),
                    pdf_url=location.get("pdf_url"),
                    license=location.get("license"),
                    host_type=source.get("type") if isinstance(source, dict) else None,
                    version=location.get("version"),
                    is_oa=is_oa,
                    provenance_hash=payload_hash(location),
                    metadata={
                        "oa_status": open_access.get("oa_status")
                        if isinstance(open_access, dict)
                        else None
                    },
                )
            )
        return result
