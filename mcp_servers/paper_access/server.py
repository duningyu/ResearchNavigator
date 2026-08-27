"""Legal-access and user-upload paper MCP tools."""

from __future__ import annotations

import re
from typing import Any

from mcp_servers.client import ResearchNavigatorClient
from mcp_servers.compat import MCP_SDK_AVAILABLE, create_server, register_tool

mcp = create_server("research-navigator-paper-access")


@register_tool(mcp, "resolve_doi")
async def resolve_doi(doi: str) -> dict[str, Any]:
    """Normalize a DOI without downloading or bypassing publisher content."""
    normalized = doi.strip().lower()
    normalized = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", normalized)
    if not normalized.startswith("10.") or "/" not in normalized:
        raise ValueError("Invalid DOI")
    return {"doi": normalized, "url": f"https://doi.org/{normalized}", "access_granted": False}


@register_tool(mcp, "resolve_arxiv")
async def resolve_arxiv(arxiv_id: str) -> dict[str, Any]:
    """Validate an arXiv identifier and return its canonical public URLs."""
    normalized = re.sub(r"^arxiv:", "", arxiv_id.strip(), flags=re.IGNORECASE)
    if not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?", normalized, re.IGNORECASE):
        raise ValueError("Invalid arXiv identifier")
    return {
        "arxiv_id": normalized,
        "abstract_url": f"https://arxiv.org/abs/{normalized}",
        "pdf_url": f"https://arxiv.org/pdf/{normalized}",
    }


@register_tool(mcp, "check_open_access")
async def check_open_access(paper_id: int) -> dict[str, Any]:
    """Return the locally recorded open-access status and source provenance."""
    paper = await ResearchNavigatorClient().request_object("GET", f"/papers/{paper_id}")
    return {
        "paper_id": paper_id,
        "open_access_status": paper.get("open_access_status"),
        "pdf_url": paper.get("pdf_url"),
        "verified_by": paper.get("source_provenance", []),
    }


@register_tool(mcp, "fetch_open_fulltext")
async def fetch_open_fulltext(paper_id: int) -> dict[str, Any]:
    """Report accessible content.

    Downloading arbitrary publisher URLs is intentionally forbidden.
    """
    status = await ResearchNavigatorClient().request_object(
        "GET", f"/papers/{paper_id}/content-status"
    )
    return {
        "status": "locally_ingested" if status.get("documents") else "not_ingested",
        "implementation_status": "not_implemented",
        "open_fulltext_fetched": False,
        "content": status,
        "paywall_bypass": False,
    }


@register_tool(mcp, "acquire_paper_evidence")
async def acquire_paper_evidence(
    paper_id: int, project_id: int | None = None, sources: list[str] | None = None
) -> dict[str, Any]:
    """Request bounded metadata/abstract acquisition through the audited API workflow."""
    return await ResearchNavigatorClient().request_object(
        "POST",
        f"/papers/{paper_id}/acquire-evidence",
        json={"project_id": project_id, "sources": sources or []},
    )


@register_tool(mcp, "parse_uploaded_pdf")
async def parse_uploaded_pdf(
    paper_id: int, file_path: str, rights_confirmed: bool
) -> dict[str, Any]:
    """Upload a user-authorized local PDF through the real ingestion endpoint."""
    return await ResearchNavigatorClient().upload_pdf(
        paper_id, file_path, rights_confirmed=rights_confirmed
    )


@register_tool(mcp, "get_content_status")
async def get_content_status(paper_id: int) -> dict[str, Any]:
    """Return the current user's legal-content ingestion status for a paper."""
    return await ResearchNavigatorClient().request_object(
        "GET", f"/papers/{paper_id}/content-status"
    )


@register_tool(mcp, "delete_local_document")
async def delete_local_document(document_id: int) -> dict[str, Any]:
    """Delete one user-owned local document through the real API endpoint."""
    result = await ResearchNavigatorClient().request_object("DELETE", f"/documents/{document_id}")
    return {**result, "document_id": document_id, "remote_content_deleted": False}


def main() -> None:
    if not MCP_SDK_AVAILABLE:
        raise RuntimeError("Install official MCP SDK v2 before running this server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
