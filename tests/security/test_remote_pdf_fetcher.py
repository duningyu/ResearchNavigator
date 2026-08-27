from __future__ import annotations

import hashlib

import httpx
import pytest

from research_navigator.documents.security import DocumentSecurityError
from research_navigator.open_access.base import OpenAccessCandidate
from research_navigator.open_access.fetcher import SafePdfFetcher


def candidate(url: str) -> OpenAccessCandidate:
    return OpenAccessCandidate(
        source="openalex",
        source_record_id="W1",
        landing_url="https://repository.example/item/1",
        pdf_url=url,
        license="cc-by",
        normalized_license="cc-by",
        host_type="repository",
        version="acceptedVersion",
        is_oa=True,
        access_decision="auto_ingest",
        provenance_hash="a" * 64,
    )


async def public_resolver(hostname: str) -> list[str]:
    return ["93.184.216.34"]


async def test_fetcher_rejects_private_dns_and_url_userinfo() -> None:
    async def private_resolver(hostname: str) -> list[str]:
        return ["127.0.0.1"]

    fetcher = SafePdfFetcher(resolver=private_resolver)
    with pytest.raises(DocumentSecurityError, match="Private or non-routable"):
        await fetcher.fetch(candidate("https://example.org/paper.pdf"))

    fetcher = SafePdfFetcher(resolver=public_resolver)
    with pytest.raises(DocumentSecurityError, match="credentials"):
        await fetcher.fetch(candidate("https://user:secret@example.org/paper.pdf"))


async def test_fetcher_revalidates_every_redirect_hop() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://internal.example/paper.pdf"})

    async def resolver(hostname: str) -> list[str]:
        if hostname == "internal.example":
            return ["10.0.0.2"]
        return ["93.184.216.34"]

    fetcher = SafePdfFetcher(
        resolver=resolver,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DocumentSecurityError, match="Private or non-routable"):
        await fetcher.fetch(candidate("https://public.example/start"))


@pytest.mark.parametrize(
    ("content_type", "body", "match"),
    [
        ("text/html", b"<html>login</html>", "Content-Type"),
        ("application/pdf", b"not a pdf", "signature"),
    ],
)
async def test_fetcher_rejects_html_and_wrong_magic(
    content_type: str, body: bytes, match: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": content_type}, content=body)

    fetcher = SafePdfFetcher(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DocumentSecurityError, match=match):
        await fetcher.fetch(candidate("https://example.org/paper.pdf"))


async def test_fetcher_rejects_oversized_body() -> None:
    body = b"%PDF-1.4\n" + b"x" * 500

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=body)

    fetcher = SafePdfFetcher(
        max_bytes=100,
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DocumentSecurityError, match="maximum size"):
        await fetcher.fetch(candidate("https://example.org/paper.pdf"))


async def test_fetcher_streams_valid_pdf_and_records_non_secret_provenance() -> None:
    body = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("cookie") is None
        assert request.headers.get("authorization") is None
        return httpx.Response(
            200,
            headers={"Content-Type": "application/pdf", "ETag": '"abc"'},
            content=body,
        )

    fetcher = SafePdfFetcher(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    result = await fetcher.fetch(candidate("https://example.org/paper.pdf"))

    assert result.data == body
    assert result.sha256 == hashlib.sha256(body).hexdigest()
    assert result.final_url == "https://example.org/paper.pdf"
    assert result.redirect_chain == []
    assert len(result.response_hash) == 64
