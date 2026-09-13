"""Bounded retrieval for URLs already selected by a scholarly adapter."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import socket
from collections.abc import Awaitable, Callable, Sequence
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel

from research_navigator.documents.security import (
    DocumentSecurityError,
    validate_external_url,
    validate_resolved_ip,
)

Resolver = Callable[[str], Awaitable[Sequence[str]] | Sequence[str]]


class FetchedPDF(BaseModel):
    data: bytes
    content_type: str | None
    final_url: str
    sha256: str
    response_hash: str


async def _system_resolver(hostname: str) -> list[str]:
    def resolve() -> list[str]:
        return sorted({str(item[4][0]) for item in socket.getaddrinfo(hostname, 443)})

    return await asyncio.to_thread(resolve)


async def _resolve(resolver: Resolver, hostname: str) -> Sequence[str]:
    result = resolver(hostname)
    return await result if inspect.isawaitable(result) else result


async def _validate_public_url(url: str, resolver: Resolver) -> None:
    validate_external_url(url)
    hostname = urlsplit(url).hostname
    if hostname is None:
        raise DocumentSecurityError("URL hostname is required")
    addresses = await _resolve(resolver, hostname)
    if not addresses:
        raise DocumentSecurityError("URL hostname did not resolve")
    for address in addresses:
        validate_resolved_ip(address)


async def fetch_bounded_pdf(
    *,
    url: str,
    max_bytes: int,
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: Resolver = _system_resolver,
    max_redirects: int = 3,
) -> FetchedPDF:
    current = url
    chain: list[str] = []
    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        transport=transport,
        follow_redirects=False,
        headers={"Accept": "application/pdf"},
    ) as client:
        for hop in range(max_redirects + 1):
            await _validate_public_url(current, resolver)
            response = await client.get(current)
            try:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location or hop >= max_redirects:
                        raise DocumentSecurityError("Remote PDF exceeded redirect limit")
                    current = urljoin(current, location)
                    chain.append(current)
                    continue
                if not 200 <= response.status_code < 300:
                    raise DocumentSecurityError("Remote PDF response was not successful")
                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit() and int(content_length) > max_bytes:
                    raise DocumentSecurityError("Remote PDF exceeds maximum size")
                data = response.content
                if len(data) > max_bytes:
                    raise DocumentSecurityError("Remote PDF exceeds maximum size")
                if not data.startswith(b"%PDF-"):
                    raise DocumentSecurityError("Remote content failed PDF signature validation")
                content_type = response.headers.get("Content-Type")
                response_hash = hashlib.sha256(
                    (current + "\n" + str(response.status_code) + "\n" + ",".join(chain)).encode()
                ).hexdigest()
                return FetchedPDF(
                    data=data,
                    content_type=content_type.split(";", 1)[0].strip().lower()
                    if content_type
                    else None,
                    final_url=current,
                    sha256=hashlib.sha256(data).hexdigest(),
                    response_hash=response_hash,
                )
            finally:
                await response.aclose()
    raise DocumentSecurityError("Remote PDF could not be fetched")
