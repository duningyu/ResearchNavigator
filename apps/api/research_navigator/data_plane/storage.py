"""Durable storage seam with local default and injectable S3-compatible transport."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast


class StorageKeyError(ValueError):
    pass


def _safe_key(key: str) -> str:
    normalized = key.replace("\\", "/").strip("/")
    if not normalized or normalized.startswith("/") or ".." in normalized.split("/"):
        raise StorageKeyError("Invalid storage key")
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", normalized):
        raise StorageKeyError("Invalid storage key")
    return normalized


class DurableStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / _safe_key(key)).resolve()
        if not path.is_relative_to(self.root):
            raise StorageKeyError("Storage key escapes root")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Transport(Protocol):
    def put_object(self, *, bucket: str, key: str, data: bytes) -> None: ...

    def get_object(self, *, bucket: str, key: str) -> bytes: ...

    def delete_object(self, *, bucket: str, key: str) -> None: ...


class _ReadableBody(Protocol):
    def read(self) -> bytes: ...

    def close(self) -> None: ...


class _Boto3Client(Protocol):
    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> object: ...

    def get_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]: ...

    def head_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]: ...

    def delete_object(self, *, Bucket: str, Key: str) -> object: ...

    def generate_presigned_url(
        self, *, ClientMethod: str, Params: Mapping[str, object], ExpiresIn: int
    ) -> str: ...


class S3TransportWithStat(S3Transport, Protocol):
    def stat_object(self, *, bucket: str, key: str) -> dict[str, object]: ...


class RuntimeStorageSettings(Protocol):
    @property
    def storage_backend(self) -> str: ...

    @property
    def upload_dir(self) -> Path: ...

    @property
    def r2_account_id(self) -> str | None: ...

    @property
    def r2_access_key_id(self) -> str | None: ...

    @property
    def r2_secret_access_key(self) -> str | None: ...

    @property
    def r2_endpoint(self) -> str | None: ...

    @property
    def r2_region(self) -> str: ...

    @property
    def r2_bucket(self) -> str | None: ...


class Boto3R2Transport:
    """Minimal S3-compatible transport for Cloudflare R2."""

    def __init__(self, client: _Boto3Client) -> None:
        self.client = client

    def put_object(self, *, bucket: str, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=bucket, Key=key, Body=data)

    def get_object(self, *, bucket: str, key: str) -> bytes:
        response = self.client.get_object(Bucket=bucket, Key=key)
        body = cast(_ReadableBody, response["Body"])
        try:
            return body.read()
        finally:
            body.close()

    def stat_object(self, *, bucket: str, key: str) -> dict[str, object]:
        return dict(self.client.head_object(Bucket=bucket, Key=key))

    def delete_object(self, *, bucket: str, key: str) -> None:
        self.client.delete_object(Bucket=bucket, Key=key)

    def generate_presigned_upload(
        self, *, bucket: str, key: str, content_type: str, sha256: str, expires_in: int
    ) -> str:
        return self.client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": bucket,
                "Key": key,
                "ContentType": content_type,
                "Metadata": {"sha256": sha256},
            },
            ExpiresIn=expires_in,
        )


class S3TransportWithPresign(S3Transport, Protocol):
    def generate_presigned_upload(
        self, *, bucket: str, key: str, content_type: str, sha256: str, expires_in: int
    ) -> str: ...


class R2Storage:
    def __init__(self, *, bucket: str, transport: S3Transport) -> None:
        self.bucket = bucket
        self.transport = transport

    def put(self, key: str, data: bytes) -> None:
        self.transport.put_object(bucket=self.bucket, key=_safe_key(key), data=data)

    def get(self, key: str) -> bytes:
        return self.transport.get_object(bucket=self.bucket, key=_safe_key(key))

    def stat(self, key: str) -> dict[str, object]:
        if not hasattr(self.transport, "stat_object"):
            raise NotImplementedError("R2 transport does not support stat")
        return cast(S3TransportWithStat, self.transport).stat_object(
            bucket=self.bucket, key=_safe_key(key)
        )

    def delete(self, key: str) -> None:
        self.transport.delete_object(bucket=self.bucket, key=_safe_key(key))

    def generate_presigned_upload(
        self, *, key: str, content_type: str, sha256: str, expires_in: int
    ) -> str:
        if not hasattr(self.transport, "generate_presigned_upload"):
            raise NotImplementedError("R2 transport does not support presigned uploads")
        return cast(S3TransportWithPresign, self.transport).generate_presigned_upload(
            bucket=self.bucket,
            key=_safe_key(key),
            content_type=content_type,
            sha256=sha256,
            expires_in=expires_in,
        )


def build_runtime_storage(settings: RuntimeStorageSettings) -> DurableStorage:
    """Build the configured storage once at the API/worker composition boundary."""
    backend = settings.storage_backend
    if backend.strip().lower() != "r2":
        return build_storage(
            backend=backend,
            local_root=settings.upload_dir,
        )

    import boto3  # type: ignore[import-untyped]
    from botocore.config import Config  # type: ignore[import-untyped]

    account_id = settings.r2_account_id
    endpoint = settings.r2_endpoint or (
        f"https://{account_id}.r2.cloudflarestorage.com"
    )
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=settings.r2_region,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    return build_storage(
        backend="r2",
        local_root=settings.upload_dir,
        r2_bucket=settings.r2_bucket,
        r2_transport=Boto3R2Transport(client),
    )


def build_storage(*, backend: str, local_root: Path, r2_bucket: str | None = None,
                  r2_transport: S3Transport | None = None) -> DurableStorage:
    normalized = backend.strip().lower()
    if normalized == "local":
        return LocalStorage(local_root)
    if normalized == "r2" and r2_bucket and r2_transport:
        return R2Storage(bucket=r2_bucket, transport=r2_transport)
    if normalized == "r2":
        raise ValueError("R2 storage requires bucket and transport")
    raise ValueError(f"Unsupported storage backend: {backend!r}")
