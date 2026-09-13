import httpx
import pytest

from research_navigator.documents.remote_fetch import fetch_bounded_pdf
from research_navigator.documents.security import DocumentSecurityError


@pytest.mark.anyio
@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/paper.pdf",
        "data:application/pdf;base64,JVBERi0x",
        "http://localhost/paper.pdf",
        "http://127.0.0.1/paper.pdf",
        "http://10.0.0.5/paper.pdf",
    ],
)
async def test_fetch_rejects_non_public_urls_before_download(url: str) -> None:
    with pytest.raises(DocumentSecurityError):
        await fetch_bounded_pdf(url=url, max_bytes=1024, timeout_seconds=1)


@pytest.mark.anyio
async def test_fetch_accepts_pdf_signature_without_requiring_content_type() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"%PDF-1.7\nbody",
            headers={"Content-Type": "text/plain"},
        )

    transport = httpx.MockTransport(handler)
    fetched = await fetch_bounded_pdf(
        url="https://repository.example/paper.pdf",
        max_bytes=1024,
        timeout_seconds=1,
        transport=transport,
        resolver=lambda _: ["93.184.216.34"],
    )
    assert fetched.data.startswith(b"%PDF-")
    assert fetched.content_type == "text/plain"


@pytest.mark.anyio
async def test_fetch_rejects_non_pdf_content() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<!doctype html>")

    with pytest.raises(DocumentSecurityError):
        await fetch_bounded_pdf(
            url="https://repository.example/paper.pdf",
            max_bytes=1024,
            timeout_seconds=1,
            transport=httpx.MockTransport(handler),
            resolver=lambda _: ["93.184.216.34"],
        )
