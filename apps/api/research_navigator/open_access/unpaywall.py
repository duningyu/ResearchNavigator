"""Unpaywall DOI OA-location resolver."""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import quote

import httpx

from research_navigator.open_access.base import (
    OpenAccessCandidate,
    PaperIdentity,
    payload_hash,
)


class UnpaywallOpenAccessClient:
    name = "unpaywall"
    base_url = "https://api.unpaywall.org/v2"

    def __init__(
        self,
        *,
        email: str | None,
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.email = email
        self.timeout = timeout
        self.transport = transport

    async def resolve(self, identity: PaperIdentity) -> list[OpenAccessCandidate]:
        if not identity.doi or not self.email:
            return []
        doi = identity.doi.removeprefix("https://doi.org/")
        url = f"{self.base_url}/{quote(doi, safe='')}"
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.get(url, params={"email": self.email})
            response.raise_for_status()
            payload = cast(dict[str, Any], response.json())
        locations: list[dict[str, Any]] = []
        for item in payload.get("oa_locations") or []:
            if isinstance(item, dict):
                locations.append(cast(dict[str, Any], item))
        if not locations and isinstance(payload.get("best_oa_location"), dict):
            locations.append(cast(dict[str, Any], payload["best_oa_location"]))
        is_oa = bool(payload.get("is_oa"))
        record_id = str(payload.get("doi") or doi)
        return [
            OpenAccessCandidate(
                source=self.name,
                source_record_id=record_id,
                landing_url=location.get("url") or location.get("url_for_landing_page"),
                pdf_url=location.get("url_for_pdf"),
                license=location.get("license"),
                host_type=location.get("host_type"),
                version=location.get("version"),
                is_oa=is_oa,
                provenance_hash=payload_hash(location),
            )
            for location in locations
        ]
