"""Semantic Scholar openAccessPdf resolver."""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import quote

import httpx

from research_navigator.open_access.base import (
    OpenAccessCandidate,
    PaperIdentity,
    payload_hash,
)


class SemanticScholarOpenAccessClient:
    name = "semantic_scholar"
    base_url = "https://api.semanticscholar.org/graph/v1/paper"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport

    async def resolve(self, identity: PaperIdentity) -> list[OpenAccessCandidate]:
        if identity.doi:
            identifier = f"DOI:{identity.doi.removeprefix('https://doi.org/')}"
        elif identity.arxiv_id:
            identifier = f"ARXIV:{identity.arxiv_id}"
        else:
            return []
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        url = f"{self.base_url}/{quote(identifier, safe=':')}"
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport, headers=headers
        ) as client:
            response = await client.get(
                url, params={"fields": "paperId,url,openAccessPdf,externalIds"}
            )
            response.raise_for_status()
            payload = cast(dict[str, Any], response.json())
        oa_pdf = payload.get("openAccessPdf")
        if not isinstance(oa_pdf, dict) or not oa_pdf.get("url"):
            return []
        pdf = cast(dict[str, Any], oa_pdf)
        return [
            OpenAccessCandidate(
                source=self.name,
                source_record_id=str(payload.get("paperId") or identifier),
                landing_url=payload.get("url"),
                pdf_url=pdf.get("url"),
                license=pdf.get("license"),
                host_type="repository",
                version=pdf.get("status"),
                is_oa=True,
                provenance_hash=payload_hash(pdf),
            )
        ]
