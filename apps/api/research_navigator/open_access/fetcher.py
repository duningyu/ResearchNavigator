"""Redirect-safe, bounded remote PDF retrieval."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import socket
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel, Field

from research_navigator.documents.security import (
    DocumentSecurityError,
    validate_external_url,
    validate_resolved_ip,
)
from research_navigator.open_access.base import OpenAccessCandidate

Resolver = Callable[[str], Awaitable[Sequence[str]] | Sequence[str]]
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_ALLOWED_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}


class PdfFetchResult(BaseModel):
    final_url: str
    data: bytes
    sha256: str
    size_bytes: int
    content_type: str
    response_hash: str
    retrieved_at: datetime
    redirect_chain: list[str] = Field(default_factory=list)


async def _default_resolver(hostname: str) -> list[str]:
    def resolve() -> list[str]:
        records = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        return sorted({str(record[4][0]) for record in records})

    return await asyncio.to_thread(resolve)


async def _resolve(resolver: Resolver, hostname: str) -> Sequence[str]:
    result = resolver(hostname)
    if inspect.isawaitable(result):
        return await result
    return result


class SafePdfFetcher:
    def __init__(
        self,
        *,
        max_bytes: int = 25 * 1024 * 1024,
        max_redirects: int = 3,
        timeout: float = 30.0,
        resolver: Resolver = _default_resolver,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.timeout = timeout
        self.resolver = resolver
        self.transport = transport

    async def _validate_hop(self, url: str) -> None:
        validate_external_url(url)
        hostname = urlsplit(url).hostname
        if hostname is None:
            raise DocumentSecurityError("URL hostname is required")
        addresses = await _resolve(self.resolver, hostname)
        if not addresses:
            raise DocumentSecurityError("URL hostname did not resolve")
        for address in addresses:
            validate_resolved_ip(address)

    async def fetch(self, candidate: OpenAccessCandidate) -> PdfFetchResult:
        if candidate.pdf_url is None:
            raise DocumentSecurityError("OA candidate does not provide a PDF URL")
        if candidate.access_decision not in {"auto_ingest", "requires_user_confirmation"}:
            raise DocumentSecurityError("OA policy does not permit PDF retrieval")

        current_url = candidate.pdf_url
        redirects: list[str] = []
        async with httpx.AsyncClient(
            timeout=self.timeout,
            transport=self.transport,
            follow_redirects=False,
            headers={"Accept": "application/pdf"},
            cookies=None,
        ) as client:
            for hop in range(self.max_redirects + 1):
                await self._validate_hop(current_url)
                request = client.build_request("GET", current_url)
                response = await client.send(request, stream=True)
                try:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("Location")
                        if not location:
                            raise DocumentSecurityError("Redirect response omitted Location")
                        if hop >= self.max_redirects:
                            raise DocumentSecurityError("Remote PDF exceeded redirect limit")
                        next_url = urljoin(current_url, location)
                        redirects.append(next_url)
                        current_url = next_url
                        continue
                    response.raise_for_status()
                    raw_content_type = response.headers.get("Content-Type", "")
                    content_type = raw_content_type.split(";", 1)[0].strip().lower()
                    if content_type not in _ALLOWED_CONTENT_TYPES:
                        raise DocumentSecurityError(
                            "Remote PDF Content-Type must be application/pdf"
                        )
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        try:
                            if int(content_length) > self.max_bytes:
                                raise DocumentSecurityError("Remote PDF exceeds maximum size")
                        except ValueError:
                            pass
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise DocumentSecurityError("Remote PDF exceeds maximum size")
                        chunks.append(chunk)
                    data = b"".join(chunks)
                    if not data.startswith(b"%PDF-"):
                        raise DocumentSecurityError(
                            "Remote content failed PDF signature validation"
                        )
                    response_metadata = {
                        "final_url": current_url,
                        "status_code": response.status_code,
                        "content_type": content_type,
                        "content_length": response.headers.get("Content-Length"),
                        "etag": response.headers.get("ETag"),
                        "last_modified": response.headers.get("Last-Modified"),
                        "redirect_chain": redirects,
                    }
                    response_hash = hashlib.sha256(
                        json.dumps(
                            response_metadata,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest()
                    return PdfFetchResult(
                        final_url=current_url,
                        data=data,
                        sha256=hashlib.sha256(data).hexdigest(),
                        size_bytes=len(data),
                        content_type=content_type,
                        response_hash=response_hash,
                        retrieved_at=datetime.now(UTC),
                        redirect_chain=redirects,
                    )
                finally:
                    await response.aclose()
        raise DocumentSecurityError("Remote PDF could not be fetched")
