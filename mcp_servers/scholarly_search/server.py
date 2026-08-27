"""Bounded scholarly search MCP tools."""

from __future__ import annotations

from typing import Any

from mcp_servers.client import ResearchNavigatorClient
from mcp_servers.compat import MCP_SDK_AVAILABLE, create_server, register_tool

mcp = create_server("research-navigator-scholarly-search")


@register_tool(mcp, "search_papers")
async def search_papers(
    query: str,
    sources: list[str] | None = None,
    limit: int = 20,
    project_id: int | None = None,
) -> dict[str, Any]:
    """Search enabled scholarly sources and return normalized records with provenance."""
    return await ResearchNavigatorClient().request_object(
        "POST",
        "/search/papers",
        json={"query": query, "sources": sources or [], "limit": limit, "project_id": project_id},
    )


@register_tool(mcp, "get_paper_metadata")
async def get_paper_metadata(paper_id: int) -> dict[str, Any]:
    """Read a normalized paper record and its source provenance."""
    return await ResearchNavigatorClient().request_object("GET", f"/papers/{paper_id}")


@register_tool(mcp, "get_related_papers")
async def get_related_papers(paper_id: int, limit: int = 10) -> dict[str, Any]:
    """Request related papers; the API reports if the relation endpoint is unavailable."""
    client = ResearchNavigatorClient()
    try:
        return await client.request_object(
            "GET", f"/papers/{paper_id}/related", params={"limit": limit}
        )
    except Exception as exc:
        return {
            "status": "unavailable",
            "paper_id": paper_id,
            "detail": str(exc),
            "provenance": "local_api",
        }


async def _bounded_relation(paper_id: int, relation: str, limit: int) -> dict[str, Any]:
    client = ResearchNavigatorClient()
    try:
        return await client.request_object(
            "GET", f"/papers/{paper_id}/{relation}", params={"limit": limit}
        )
    except Exception as exc:
        return {
            "status": "unavailable",
            "paper_id": paper_id,
            "relation": relation,
            "detail": str(exc),
            "provenance": "local_api",
        }


@register_tool(mcp, "get_references")
async def get_references(paper_id: int, limit: int = 20) -> dict[str, Any]:
    """Fetch references when a configured source supports them."""
    return await _bounded_relation(paper_id, "references", limit)


@register_tool(mcp, "get_citations")
async def get_citations(paper_id: int, limit: int = 20) -> dict[str, Any]:
    """Fetch citations when a configured source supports them."""
    return await _bounded_relation(paper_id, "citations", limit)


@register_tool(mcp, "search_authors")
async def search_authors(query: str, limit: int = 10) -> dict[str, Any]:
    """Search authors; never merge ambiguous names without source identifiers."""
    client = ResearchNavigatorClient()
    try:
        return await client.request_object(
            "GET", "/authors", params={"query": query, "limit": limit}
        )
    except Exception as exc:
        return {
            "status": "unavailable",
            "query": query,
            "detail": str(exc),
            "author_disambiguation_required": True,
        }


@register_tool(mcp, "get_author_profile")
async def get_author_profile(author_id: str) -> dict[str, Any]:
    """Read a source-identified author profile without inferring individual contributions."""
    client = ResearchNavigatorClient()
    try:
        return await client.request_object("GET", f"/authors/{author_id}")
    except Exception as exc:
        return {
            "status": "unavailable",
            "author_id": author_id,
            "detail": str(exc),
            "contributions_inferred": False,
        }


@register_tool(mcp, "source_health_check")
async def source_health_check(source_name: str | None = None) -> dict[str, Any]:
    """Return source enablement, configuration, and connectivity state."""
    client = ResearchNavigatorClient()
    if source_name:
        return await client.request_object("POST", f"/sources/{source_name}/test")
    sources = await client.request("GET", "/sources/status")
    if not isinstance(sources, list):
        raise TypeError("Source status response must be a JSON array")
    return {"sources": sources}


def main() -> None:
    if not MCP_SDK_AVAILABLE:
        raise RuntimeError("Install official MCP SDK v2 before running this server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
