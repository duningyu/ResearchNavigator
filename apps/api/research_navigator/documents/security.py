"""Security checks for uploaded documents and remote URLs."""

from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class DocumentSecurityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    safe_filename: str
    sha256: str
    size_bytes: int


_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+")


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    name = _SAFE_FILENAME.sub("_", name)
    if not name:
        name = "paper.pdf"
    return name[:180]


def validate_pdf_upload(
    filename: str,
    content_type: str | None,
    data: bytes,
    *,
    max_bytes: int,
) -> ValidatedUpload:
    safe = _safe_filename(filename)
    if not safe.lower().endswith(".pdf"):
        raise DocumentSecurityError("A .PDF extension is required")
    if content_type not in {"application/pdf", "application/x-pdf"}:
        raise DocumentSecurityError("The upload MIME type must be application/pdf")
    if not data.startswith(b"%PDF-"):
        raise DocumentSecurityError("The file does not contain a valid PDF signature")
    if not data or len(data) > max_bytes:
        raise DocumentSecurityError(f"PDF size must be between 1 and {max_bytes} bytes")
    return ValidatedUpload(
        safe_filename=safe,
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
    )




def validate_resolved_ip(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise DocumentSecurityError("Resolved address is not a valid IP address") from exc
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise DocumentSecurityError("Private or non-routable IP addresses are not allowed")
    return str(address)


def validate_external_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise DocumentSecurityError("Only HTTP(S) URLs are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise DocumentSecurityError("URL credentials are not allowed")
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise DocumentSecurityError("URL hostname is required")
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise DocumentSecurityError("Local hostnames are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        validate_resolved_ip(str(address))
    return url
