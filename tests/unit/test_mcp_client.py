from __future__ import annotations

import httpx
import pytest
from mcp_servers.client import ResearchNavigatorClient


def test_request_timeout_is_bounded_and_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RN_MCP_TIMEOUT_SECONDS", "0.25")

    client = ResearchNavigatorClient(base_url="http://test/api", token="secret")

    assert client.timeout.read == 0.25
    assert client.timeout.connect == 0.25


@pytest.mark.asyncio
async def test_request_object_rejects_non_object_json(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_request(
        self: httpx.AsyncClient, *args: object, **kwargs: object
    ) -> httpx.Response:
        return httpx.Response(
            200, json=[{"status": "ok"}], request=httpx.Request("GET", "http://test")
        )

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    client = ResearchNavigatorClient(base_url="http://test/api", token="secret")

    with pytest.raises(TypeError, match="JSON object"):
        await client.request_object("GET", "/object")
