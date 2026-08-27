from __future__ import annotations

import httpx

from research_navigator.open_access.arxiv import ArxivOpenAccessClient
from research_navigator.open_access.base import PaperIdentity
from research_navigator.open_access.openalex import OpenAlexOpenAccessClient
from research_navigator.open_access.resolver import OpenAccessResolver
from research_navigator.open_access.semantic_scholar import SemanticScholarOpenAccessClient
from research_navigator.open_access.unpaywall import UnpaywallOpenAccessClient


async def test_openalex_client_parses_best_oa_location_and_license() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "https://openalex.org/W1",
                "open_access": {"is_oa": True, "oa_status": "green"},
                "best_oa_location": {
                    "landing_page_url": "https://repo.example/item/1",
                    "pdf_url": "https://repo.example/item/1.pdf",
                    "license": "cc-by",
                    "version": "acceptedVersion",
                    "source": {"type": "repository"},
                },
            },
        )

    client = OpenAlexOpenAccessClient(transport=httpx.MockTransport(handler))
    candidates = await client.resolve(PaperIdentity(doi="10.1000/test", title="Test"))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.pdf_url == "https://repo.example/item/1.pdf"
    assert candidate.license == "cc-by"
    assert candidate.is_oa is True
    assert len(candidate.provenance_hash) == 64


async def test_unpaywall_requires_email_and_parses_oa_locations() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["email"] == "researcher@example.com"
        return httpx.Response(
            200,
            json={
                "doi": "10.1000/test",
                "is_oa": True,
                "oa_locations": [
                    {
                        "url": "https://publisher.example/article",
                        "url_for_pdf": "https://publisher.example/article.pdf",
                        "license": None,
                        "host_type": "publisher",
                        "version": "publishedVersion",
                    }
                ],
            },
        )

    client = UnpaywallOpenAccessClient(
        email="researcher@example.com", transport=httpx.MockTransport(handler)
    )
    candidates = await client.resolve(PaperIdentity(doi="10.1000/test", title="Test"))
    assert candidates[0].source == "unpaywall"
    assert candidates[0].license is None


async def test_arxiv_and_semantic_scholar_clients_parse_open_pdf() -> None:
    arxiv_xml = b"""<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns='http://www.w3.org/2005/Atom' xmlns:arxiv='http://arxiv.org/schemas/atom'>
      <entry>
        <id>https://arxiv.org/abs/2608.12345</id>
        <title>Example</title>
        <arxiv:license>https://creativecommons.org/licenses/by/4.0/</arxiv:license>
        <link title='pdf' href='https://arxiv.org/pdf/2608.12345'/>
      </entry>
    </feed>"""

    def arxiv_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=arxiv_xml)

    arxiv = ArxivOpenAccessClient(transport=httpx.MockTransport(arxiv_handler))
    arxiv_candidates = await arxiv.resolve(
        PaperIdentity(arxiv_id="2608.12345", title="Example")
    )
    assert arxiv_candidates[0].license is not None

    def semantic_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "paperId": "S1",
                "url": "https://semanticscholar.org/paper/S1",
                "openAccessPdf": {
                    "url": "https://pdfs.semanticscholar.org/S1.pdf",
                    "status": "GREEN",
                    "license": "CCBY",
                },
            },
        )

    semantic = SemanticScholarOpenAccessClient(transport=httpx.MockTransport(semantic_handler))
    semantic_candidates = await semantic.resolve(
        PaperIdentity(doi="10.1000/test", title="Example")
    )
    assert semantic_candidates[0].pdf_url == "https://pdfs.semanticscholar.org/S1.pdf"


async def test_resolver_selects_permissive_candidate_and_keeps_source_statuses() -> None:
    def openalex_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "https://openalex.org/W1",
                "open_access": {"is_oa": True},
                "best_oa_location": {
                    "landing_page_url": "https://repo.example/item/1",
                    "pdf_url": "https://repo.example/item/1.pdf",
                    "license": "cc-by",
                    "version": "acceptedVersion",
                    "source": {"type": "repository"},
                },
            },
        )

    def unpaywall_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "doi": "10.1000/test",
                "is_oa": True,
                "oa_locations": [
                    {
                        "url": "https://unknown.example/item",
                        "url_for_pdf": "https://unknown.example/item.pdf",
                        "license": None,
                        "host_type": "repository",
                    }
                ],
            },
        )

    resolver = OpenAccessResolver(
        [
            OpenAlexOpenAccessClient(transport=httpx.MockTransport(openalex_handler)),
            UnpaywallOpenAccessClient(
                email="researcher@example.com",
                transport=httpx.MockTransport(unpaywall_handler),
            ),
        ]
    )
    resolution = await resolver.resolve(PaperIdentity(doi="10.1000/test", title="Test"))

    assert resolution.selected is not None
    assert resolution.selected.source == "openalex"
    assert resolution.selected.access_decision == "auto_ingest"
    assert resolution.source_status == {"openalex": "ok", "unpaywall": "ok"}
    assert len(resolution.candidates) == 2
