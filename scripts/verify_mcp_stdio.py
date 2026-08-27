"""Exercise all ResearchNavigator MCP servers through the official stdio client."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
API = os.getenv("RN_API_BASE_URL", "http://127.0.0.1:8000/api")


def register_user(label: str) -> tuple[str, str]:
    email = f"mcp-{label}-{time.time_ns()}@example.com"
    response = httpx.post(
        f"{API}/auth/register",
        json={"email": email, "password": "mcp-stdio-pass-123", "display_name": "MCP Audit"},
        timeout=20,
    )
    response.raise_for_status()
    return str(response.json()["access_token"]), email


def api_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def tool_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        nested = structured.get("result")
        return nested if isinstance(nested, dict) else structured
    for item in result.content:
        raw = getattr(item, "text", None)
        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    raise AssertionError(f"MCP result has no JSON object payload: {result.content}")


@asynccontextmanager
async def server_session(
    module: str,
    *,
    token: str | None,
    api_base: str = API,
    extra_environment: dict[str, str] | None = None,
) -> AsyncIterator[ClientSession]:
    environment = dict(os.environ)
    if token is None:
        environment.pop("RN_MCP_ACCESS_TOKEN", None)
    else:
        environment["RN_MCP_ACCESS_TOKEN"] = token
    environment["RN_API_BASE_URL"] = api_base
    environment.update(extra_environment or {})
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", module],
        env=environment,
        cwd=ROOT,
    )
    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as session,
    ):
        initialized = await session.initialize()
        print(f"START module={module} protocol={initialized.protocol_version}")
        yield session


async def verify_server(
    module: str,
    required_tools: set[str],
    calls: list[tuple[str, dict[str, Any]]],
    token: str,
    rejected_calls: list[tuple[str, dict[str, Any]]] | None = None,
) -> None:
    async with server_session(module, token=token) as session:
        tools = await session.list_tools()
        by_name = {tool.name: tool for tool in tools.tools}
        assert required_tools <= set(by_name)
        for tool in tools.tools:
            assert tool.description, f"{module}.{tool.name} has no description"
        for name in required_tools:
            assert by_name[name].input_schema.get("type") == "object"
            assert by_name[name].output_schema is not None
        for name, arguments in calls:
            result = await session.call_tool(name, arguments)
            assert not result.is_error, f"{module}.{name}: {result.content}"
        for name, arguments in rejected_calls or []:
            result = await session.call_tool(name, arguments)
            assert result.is_error, f"{module}.{name} unexpectedly accepted unsafe input"
        print(
            f"PASS module={module} "
            f"tools={len(tools.tools)} calls={','.join(name for name, _ in calls)}"
        )


async def verify_negative_runtime_cases(token: str) -> None:
    async with server_session(
        "mcp_servers.research_workspace.server", token=None
    ) as session:
        result = await session.call_tool("export_workspace", {})
        assert result.is_error
    print("PASS auth_missing=user_scoped_tool_rejected")

    unavailable_api = "http://127.0.0.1:1/api"
    async with server_session(
        "mcp_servers.scholarly_search.server", token=token, api_base=unavailable_api
    ) as session:
        result = await session.call_tool("search_papers", {"query": "attention", "limit": 1})
        assert result.is_error
        relation = await session.call_tool("get_related_papers", {"paper_id": 1, "limit": 1})
        assert not relation.is_error
        payload = tool_payload(relation)
        assert payload["status"] == "unavailable"
        assert payload["provenance"] == "local_api"
    print("PASS api_unavailable=error explicit_unavailable=provenance_preserved")

    connections: list[asyncio.StreamWriter] = []
    release_connections = asyncio.Event()

    async def hang(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connections.append(writer)
        try:
            await release_connections.wait()
        finally:
            writer.close()

    server = await asyncio.start_server(hang, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    elapsed = 999.0
    try:
        async with server_session(
            "mcp_servers.scholarly_search.server",
            token=token,
            api_base=f"http://127.0.0.1:{port}/api",
            extra_environment={"RN_MCP_TIMEOUT_SECONDS": "0.2"},
        ) as session:
            started = time.monotonic()
            result = await session.call_tool(
                "search_papers", {"query": "attention", "limit": 1}
            )
            elapsed = time.monotonic() - started
            assert result.is_error
    finally:
        release_connections.set()
        server.close()
        await server.wait_closed()
        for writer in connections:
            writer.close()
    assert elapsed < 5, f"timeout case exceeded bound: {elapsed:.2f}s"
    print(f"PASS timeout=bounded elapsed_seconds={elapsed:.2f}")


async def verify_user_isolation_and_real_endpoints(
    first_token: str, second_token: str, first_email: str
) -> None:
    project_name = f"private-mcp-project-{time.time_ns()}"
    async with server_session(
        "mcp_servers.research_workspace.server", token=first_token
    ) as first_session:
        created = await first_session.call_tool("create_research_project", {"name": project_name})
        assert not created.is_error
        exported = await first_session.call_tool("export_workspace", {})
        assert not exported.is_error
        assert project_name in json.dumps(tool_payload(exported), ensure_ascii=False)
        assert first_email in json.dumps(tool_payload(exported), ensure_ascii=False)
    async with server_session(
        "mcp_servers.research_workspace.server", token=second_token
    ) as second_session:
        exported = await second_session.call_tool("export_workspace", {})
        assert not exported.is_error
        assert project_name not in json.dumps(tool_payload(exported), ensure_ascii=False)
    print("PASS user_isolation=two_tokens export_workspace=real_endpoint")

    search = httpx.post(
        f"{API}/search/papers",
        headers=api_headers(first_token),
        json={"query": "anomaly detection", "sources": ["fixture"], "limit": 1},
        timeout=20,
    )
    search.raise_for_status()
    paper_id = int(search.json()["papers"][0]["id"])
    async with server_session(
        "mcp_servers.scholarly_search.server", token=first_token
    ) as search_session:
        searched = await search_session.call_tool(
            "search_papers",
            {"query": "anomaly detection", "sources": ["fixture"], "limit": 1},
        )
        assert not searched.is_error
        searched_payload = tool_payload(searched)
        paper = searched_payload["papers"][0]
        provenance = paper["source_provenance"][0]
        assert provenance["source"] == "fixture"
        assert provenance["source_id"]
        assert provenance["source_url"]
        assert provenance["is_fixture"] is True
    async with server_session("mcp_servers.paper_access.server", token=first_token) as session:
        bounded_access = await session.call_tool("fetch_open_fulltext", {"paper_id": paper_id})
        assert not bounded_access.is_error
        assert tool_payload(bounded_access)["paywall_bypass"] is False
    print("PASS provenance=explicit fixture_disclosed=true paywall_bypass=false")
    buffer = BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(72, 760, "Authorized MCP deletion verification document.")
    canvas.save()
    uploaded = httpx.post(
        f"{API}/papers/{paper_id}/upload",
        headers=api_headers(first_token),
        data={"rights_confirmed": "true"},
        files={"file": ("mcp-delete.pdf", buffer.getvalue(), "application/pdf")},
        timeout=30,
    )
    uploaded.raise_for_status()
    document_id = int(uploaded.json()["id"])

    second_status = httpx.get(
        f"{API}/papers/{paper_id}/content-status",
        headers=api_headers(second_token),
        timeout=20,
    )
    second_status.raise_for_status()
    assert all(item["id"] != document_id for item in second_status.json()["documents"])

    async with server_session("mcp_servers.paper_access.server", token=first_token) as session:
        deleted = await session.call_tool("delete_local_document", {"document_id": document_id})
        assert not deleted.is_error
        payload = tool_payload(deleted)
        assert payload["document_id"] == document_id
        assert payload["http_status"] == 204
        assert payload["remote_content_deleted"] is False
    remaining = httpx.get(
        f"{API}/papers/{paper_id}/documents",
        headers=api_headers(first_token),
        timeout=20,
    )
    remaining.raise_for_status()
    assert all(item["id"] != document_id for item in remaining.json())
    print("PASS delete_local_document=real_endpoint cross_user_document_isolation=verified")


async def main() -> None:
    token, email = register_user("a")
    second_token, _ = register_user("b")
    await verify_server(
        "mcp_servers.scholarly_search.server",
        {"search_papers", "source_health_check"},
        [
            ("search_papers", {"query": "anomaly detection", "sources": ["fixture"], "limit": 2}),
            ("source_health_check", {"source_name": "fixture"}),
        ],
        token,
    )
    await verify_negative_runtime_cases(token)
    await verify_user_isolation_and_real_endpoints(token, second_token, email)
    await verify_server(
        "mcp_servers.paper_access.server",
        {"resolve_arxiv", "get_content_status", "resolve_doi"},
        [
            ("resolve_arxiv", {"arxiv_id": "1706.03762"}),
            ("get_content_status", {"paper_id": 1}),
        ],
        token,
        rejected_calls=[("resolve_doi", {"doi": "http://169.254.169.254/latest/meta-data"})],
    )
    await verify_server(
        "mcp_servers.research_workspace.server",
        {"create_research_project", "add_note", "export_workspace"},
        [
            ("create_research_project", {"name": f"MCP project {time.time_ns()}"}),
            ("add_note", {"paper_id": 1, "content": "MCP stdio audit note"}),
            ("export_workspace", {}),
        ],
        token,
    )


if __name__ == "__main__":
    asyncio.run(main())
