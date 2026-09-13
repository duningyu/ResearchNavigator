"""Validation and short-lived signed tickets for direct R2 uploads."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass

from research_navigator.config import Settings
from research_navigator.data_plane.storage import DurableStorage, R2Storage
from research_navigator.documents.security import DocumentSecurityError, _safe_filename

PRESIGN_TTL_SECONDS = 300
MAX_PRESIGN_TTL_SECONDS = 600
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_BUCKET_MISMATCH_MESSAGE = "Upload storage target does not match current environment"


@dataclass(frozen=True, slots=True)
class PresignMetadata:
    filename: str
    content_type: str
    size_bytes: int
    sha256: str


def validated_r2_bucket(*, settings: Settings, storage: DurableStorage) -> str:
    if (
        settings.storage_backend != "r2"
        or not settings.r2_bucket
        or not isinstance(storage, R2Storage)
        or storage.bucket != settings.r2_bucket
    ):
        raise DocumentSecurityError(_BUCKET_MISMATCH_MESSAGE)
    return settings.r2_bucket


def validate_completion_token_bucket(
    *, settings: Settings, storage: DurableStorage, claim_bucket: object
) -> str:
    bucket = validated_r2_bucket(settings=settings, storage=storage)
    if not isinstance(claim_bucket, str) or claim_bucket != bucket:
        raise DocumentSecurityError(_BUCKET_MISMATCH_MESSAGE)
    return bucket


def validate_presign_metadata(
    *, filename: str, content_type: str, size_bytes: int, sha256: str, max_bytes: int
) -> PresignMetadata:
    safe_filename = _safe_filename(filename)
    if not safe_filename.lower().endswith(".pdf"):
        raise DocumentSecurityError("A .PDF extension is required")
    normalized_content_type = content_type.strip().lower()
    if normalized_content_type not in {"application/pdf", "application/x-pdf"}:
        raise DocumentSecurityError("The upload MIME type must be application/pdf")
    if size_bytes <= 0 or size_bytes > max_bytes:
        raise DocumentSecurityError(f"PDF size must be between 1 and {max_bytes} bytes")
    if not _SHA256.fullmatch(sha256):
        raise DocumentSecurityError("sha256 must be a 64-character hexadecimal digest")
    return PresignMetadata(safe_filename, normalized_content_type, size_bytes, sha256.lower())


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_completion_token(
    *, secret: str, claims: dict[str, object], now: int | None = None
) -> str:
    payload = dict(claims)
    expiry = payload.get("exp", (now or int(time.time())) + PRESIGN_TTL_SECONDS)
    if not isinstance(expiry, (int, str, float)):
        raise DocumentSecurityError("Invalid upload completion expiry")
    payload["exp"] = int(expiry)
    body = _encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_encode(signature)}"


def verify_completion_token(
    *, secret: str, token: str, now: int | None = None
) -> dict[str, object]:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _decode(signature)):
            raise ValueError("signature")
        claims = json.loads(_decode(body))
        if not isinstance(claims, dict) or int(claims["exp"]) < int(now or time.time()):
            raise ValueError("expired")
        return claims
    except (
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        UnicodeError,
        binascii.Error,
    ) as exc:
        raise DocumentSecurityError("Invalid or expired upload completion token") from exc


def redact_presigned_url(url: str) -> str:
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
