"""arXiv metadata and license resolver."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET

import httpx

from research_navigator.open_access.base import OpenAccessCandidate, PaperIdentity

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"


class ArxivOpenAccessClient:
    name = "arxiv"
    base_url = "https://export.arxiv.org/api/query"

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.timeout = timeout
        self.transport = transport

    async def resolve(self, identity: PaperIdentity) -> list[OpenAccessCandidate]:
        if not identity.arxiv_id:
            return []
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.get(self.base_url, params={"id_list": identity.arxiv_id})
            response.raise_for_status()
            content = response.content
        root = ET.fromstring(content)
        entry = root.find(f"{_ATOM}entry")
        if entry is None:
            return []
        entry_id = entry.findtext(f"{_ATOM}id") or f"https://arxiv.org/abs/{identity.arxiv_id}"
        license_url = entry.findtext(f"{_ARXIV}license")
        pdf_url = None
        for link in entry.findall(f"{_ATOM}link"):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href")
                break
        return [
            OpenAccessCandidate(
                source=self.name,
                source_record_id=identity.arxiv_id,
                landing_url=entry_id,
                pdf_url=pdf_url,
                license=license_url,
                host_type="repository",
                version="submittedVersion",
                is_oa=True,
                provenance_hash=hashlib.sha256(ET.tostring(entry)).hexdigest(),
                metadata={"terms_note": "arXiv license governs automated storage and redistribution"},
            )
        ]
