import pytest
from mcp_servers.client import ResearchNavigatorClient
from mcp_servers.compat import registered_tool_names
from mcp_servers.paper_access.server import acquire_paper_evidence, fetch_open_fulltext
from mcp_servers.paper_access.server import mcp as access_server
from mcp_servers.research_workspace.server import mcp as workspace_server
from mcp_servers.scholarly_search.server import mcp as search_server


def test_scholarly_search_mcp_exposes_required_bounded_tools() -> None:
    assert registered_tool_names(search_server) >= {
        "search_papers",
        "get_paper_metadata",
        "get_related_papers",
        "get_references",
        "get_citations",
        "search_authors",
        "get_author_profile",
        "source_health_check",
    }


def test_paper_access_mcp_exposes_required_tools() -> None:
    assert registered_tool_names(access_server) >= {
        "resolve_doi",
        "resolve_arxiv",
        "check_open_access",
        "fetch_open_fulltext",
        "acquire_paper_evidence",
        "parse_uploaded_pdf",
        "get_content_status",
        "delete_local_document",
    }


@pytest.mark.asyncio
async def test_acquire_paper_evidence_mcp_submits_a_bounded_api_request(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def request_object(
        self: ResearchNavigatorClient, method: str, path: str, **kwargs: object
    ) -> dict[str, object]:
        captured.update({"method": method, "path": path, **kwargs})
        return {"outcome": "no_matching_evidence"}

    monkeypatch.setattr(ResearchNavigatorClient, "request_object", request_object)

    result = await acquire_paper_evidence(7, project_id=3, sources=["crossref"])

    assert result == {"outcome": "no_matching_evidence"}
    assert captured == {
        "method": "POST",
        "path": "/papers/7/acquire-evidence",
        "json": {"project_id": 3, "sources": ["crossref"]},
    }


@pytest.mark.asyncio
async def test_fetch_open_fulltext_explicitly_reports_not_implemented(monkeypatch) -> None:
    async def request_object(
        self: ResearchNavigatorClient, method: str, path: str, **kwargs: object
    ) -> dict[str, object]:
        return {
            "documents": [
                {"id": 9, "evidence_level": "user_uploaded_fulltext"}
            ]
        }

    monkeypatch.setattr(ResearchNavigatorClient, "request_object", request_object)

    result = await fetch_open_fulltext(7)

    assert result["implementation_status"] == "not_implemented"
    assert result["open_fulltext_fetched"] is False
    assert result["status"] == "locally_ingested"


def test_workspace_mcp_exposes_required_user_scoped_tools() -> None:
    assert registered_tool_names(workspace_server) >= {
        "create_research_project",
        "update_research_profile",
        "save_paper",
        "add_note",
        "update_reading_status",
        "create_gap_candidate",
        "confirm_gap_candidate",
        "create_research_plan",
        "update_plan_item",
        "export_workspace",
    }
