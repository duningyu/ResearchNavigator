"""Durable storage seam with local default and injectable S3-compatible transport."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol


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


class R2Storage:
    def __init__(self, *, bucket: str, transport: S3Transport) -> None:
        self.bucket = bucket
        self.transport = transport

    def put(self, key: str, data: bytes) -> None:
        self.transport.put_object(bucket=self.bucket, key=_safe_key(key), data=data)

    def get(self, key: str) -> bytes:
        return self.transport.get_object(bucket=self.bucket, key=_safe_key(key))

    def delete(self, key: str) -> None:
        self.transport.delete_object(bucket=self.bucket, key=_safe_key(key))


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
