"""User-scoped research workspace MCP tools."""

from __future__ import annotations

from typing import Any

from mcp_servers.client import ResearchNavigatorClient
from mcp_servers.compat import MCP_SDK_AVAILABLE, create_server, register_tool

mcp = create_server("research-navigator-workspace")


@register_tool(mcp, "create_research_project")
async def create_research_project(
    name: str, broad_direction: str | None = None, description: str | None = None
) -> dict[str, Any]:
    """Create a user-scoped research project."""
    return await ResearchNavigatorClient().request_object(
        "POST",
        "/projects",
        json={"name": name, "broad_direction": broad_direction, "description": description},
    )


@register_tool(mcp, "update_research_profile")
async def update_research_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Update the authenticated user's research profile."""
    return await ResearchNavigatorClient().request_object(
        "PUT", "/research-profiles/me", json=profile
    )


@register_tool(mcp, "save_paper")
async def save_paper(paper_id: int) -> dict[str, Any]:
    """Save a paper to the authenticated user's library."""
    return await ResearchNavigatorClient().request_object(
        "POST", "/library/favorites", json={"paper_id": paper_id}
    )


@register_tool(mcp, "add_note")
async def add_note(paper_id: int, content: str, note_type: str = "user_note") -> dict[str, Any]:
    """Add a user-scoped note to a paper."""
    return await ResearchNavigatorClient().request_object(
        "POST",
        "/library/notes",
        json={"paper_id": paper_id, "content": content, "note_type": note_type},
    )


@register_tool(mcp, "update_reading_status")
async def update_reading_status(paper_id: int, status: str, progress: int = 0) -> dict[str, Any]:
    """Update a paper's reading status for the authenticated user."""
    return await ResearchNavigatorClient().request_object(
        "PUT",
        f"/library/papers/{paper_id}/reading-status",
        json={"status": status, "progress": progress},
    )


@register_tool(mcp, "create_gap_candidate")
async def create_gap_candidate(project_id: int, paper_ids: list[int]) -> dict[str, Any]:
    """Generate bounded candidate gaps from an explicit paper set."""
    return await ResearchNavigatorClient().request_object(
        "POST", "/gaps/generate", json={"project_id": project_id, "paper_ids": paper_ids}
    )


@register_tool(mcp, "confirm_gap_candidate")
async def confirm_gap_candidate(
    gap_id: int, confirmed: bool, note: str | None = None
) -> dict[str, Any]:
    """Record an explicit authenticated user's gap confirmation decision."""
    return await ResearchNavigatorClient().request_object(
        "POST", f"/gaps/{gap_id}/confirm", json={"confirmed": confirmed, "note": note}
    )


@register_tool(mcp, "create_research_plan")
async def create_research_plan(
    project_id: int, gap_id: int, title: str | None = None
) -> dict[str, Any]:
    """Create a plan only after the referenced gap passes its human gate."""
    return await ResearchNavigatorClient().request_object(
        "POST", "/plans", json={"project_id": project_id, "gap_id": gap_id, "title": title}
    )


@register_tool(mcp, "update_plan_item")
async def update_plan_item(
    item_id: int, status: str | None = None, notes: str | None = None
) -> dict[str, Any]:
    """Update one user-owned research plan item."""
    return await ResearchNavigatorClient().request_object(
        "PUT", f"/plan-items/{item_id}", json={"status": status, "notes": notes}
    )


@register_tool(mcp, "export_workspace")
async def export_workspace() -> dict[str, Any]:
    """Export only the authenticated user's workspace through the API."""
    return await ResearchNavigatorClient().request_object("GET", "/workspace/export")


def main() -> None:
    if not MCP_SDK_AVAILABLE:
        raise RuntimeError("Install official MCP SDK v2 before running this server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
