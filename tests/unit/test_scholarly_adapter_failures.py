from __future__ import annotations

import httpx
import pytest

from research_navigator.scholarly.arxiv import ArxivAdapter
from research_navigator.scholarly.base import ScholarlyAdapter, SearchRequest
from research_navigator.scholarly.crossref import CrossrefAdapter
from research_navigator.scholarly.openalex import OpenAlexAdapter
from research_navigator.scholarly.semantic_scholar import SemanticScholarAdapter


async def test_openalex_adapter_sends_configured_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def successful(*args: object, **kwargs: object) -> httpx.Response:
        captured.update(kwargs)
        return httpx.Response(
            200,
            json={"results": []},
            request=httpx.Request("GET", "https://api.openalex.org/works"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", successful)
    adapter = OpenAlexAdapter(api_key="openalex-secret")

    result = await adapter.search(SearchRequest(query="test", limit=1))

    assert result.status.status == "ok"
    assert captured["params"]["api_key"] == "openalex-secret"  # type: ignore[index]


@pytest.mark.parametrize("adapter", [OpenAlexAdapter(), CrossrefAdapter(), ArxivAdapter()])
async def test_live_adapter_reports_rate_limit(
    adapter: ScholarlyAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def rate_limited(*args: object, **kwargs: object) -> httpx.Response:
        return httpx.Response(429, request=httpx.Request("GET", "https://source.invalid"))

    monkeypatch.setattr(httpx.AsyncClient, "get", rate_limited)
    result = await adapter.search(SearchRequest(query="test", limit=1))
    assert result.records == []
    assert result.status.status == "rate_limited"


@pytest.mark.parametrize("adapter", [OpenAlexAdapter(), CrossrefAdapter(), ArxivAdapter()])
async def test_live_adapter_reports_timeout(
    adapter: ScholarlyAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def timeout(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ReadTimeout("controlled timeout")

    monkeypatch.setattr(httpx.AsyncClient, "get", timeout)
    result = await adapter.search(SearchRequest(query="test", limit=1))
    assert result.records == []
    assert result.status.status == "error"
    assert "ReadTimeout" in (result.status.detail or "")


@pytest.mark.parametrize(
    ("adapter", "response"),
    [
        (
            OpenAlexAdapter(),
            httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "https://openalex.org/W1",
                            "display_name": "Verified abstract",
                            "publication_year": 2026,
                            "ids": {"doi": "https://doi.org/10.1000/verified"},
                            "abstract_inverted_index": {"Verified": [0], "evidence": [1]},
                        }
                    ]
                },
                request=httpx.Request("GET", "https://api.openalex.org/works"),
            ),
        ),
        (
            CrossrefAdapter(),
            httpx.Response(
                200,
                json={
                    "message": {
                        "items": [
                            {
                                "DOI": "10.1000/verified",
                                "title": ["Verified abstract"],
                                "abstract": "Verified evidence",
                            }
                        ]
                    }
                },
                request=httpx.Request("GET", "https://api.crossref.org/works"),
            ),
        ),
        (
            SemanticScholarAdapter(),
            httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "paperId": "S1",
                            "title": "Verified abstract",
                            "abstract": "Verified evidence",
                            "externalIds": {"DOI": "10.1000/verified"},
                        }
                    ]
                },
                request=httpx.Request("GET", "https://api.semanticscholar.org/graph/v1/paper/search"),
            ),
        ),
        (
            ArxivAdapter(),
            httpx.Response(
                200,
                content=b"""<?xml version='1.0' encoding='UTF-8'?>
                <feed xmlns='http://www.w3.org/2005/Atom'>
                  <entry><id>https://arxiv.org/abs/2608.12345</id>
                  <title>Verified abstract</title><summary>Verified evidence</summary>
                  <published>2026-08-01T00:00:00Z</published></entry>
                </feed>""",
                request=httpx.Request("GET", "https://export.arxiv.org/api/query"),
            ),
        ),
    ],
)
async def test_official_adapter_binds_abstract_to_exact_provenance(
    adapter: ScholarlyAdapter,
    response: httpx.Response,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def successful(*args: object, **kwargs: object) -> httpx.Response:
        return response

    monkeypatch.setattr(httpx.AsyncClient, "get", successful)

    result = await adapter.search(SearchRequest(query="verified", limit=1))

    assert len(result.records) == 1, result.status
    record = result.records[0]
    assert record.abstract
    assert record.abstract_provenance == record.source_provenance[0]
    assert record.abstract_provenance.is_fixture is False
