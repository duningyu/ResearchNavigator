from __future__ import annotations

import httpx
import pytest

from research_navigator.scholarly.base import SearchRequest
from research_navigator.scholarly.openalex import OpenAlexAdapter


async def test_openalex_rate_limit_status_preserves_non_secret_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def rate_limited(*args: object, **kwargs: object) -> httpx.Response:
        return httpx.Response(
            429,
            headers={
                "X-RateLimit-Limit": "1000",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "2026-08-28T01:02:03Z",
                "Retry-After": "30",
            },
            request=httpx.Request("GET", "https://api.openalex.org/works"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", rate_limited)
    result = await OpenAlexAdapter(api_key="server-secret").search(
        SearchRequest(query="attention", limit=1)
    )

    assert result.status.status == "rate_limited"
    assert result.status.metadata == {
        "http_status": 429,
        "rate_limit_limit": 1000,
        "rate_limit_remaining": 0,
        "rate_limit_reset": "2026-08-28T01:02:03Z",
        "retry_after_seconds": 30,
    }
    assert "server-secret" not in str(result.status.model_dump())


async def test_openalex_success_preserves_rate_limit_budget_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def successful(*args: object, **kwargs: object) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "X-RateLimit-Limit": "1000",
                "X-RateLimit-Remaining": "998",
            },
            json={"results": []},
            request=httpx.Request("GET", "https://api.openalex.org/works"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", successful)
    result = await OpenAlexAdapter().search(SearchRequest(query="attention", limit=1))

    assert result.status.status == "ok"
    assert result.status.metadata["http_status"] == 200
    assert result.status.metadata["rate_limit_remaining"] == 998
