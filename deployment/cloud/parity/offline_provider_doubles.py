"""Deterministic provider doubles for the no-network parity harness."""

from __future__ import annotations

from pathlib import Path

from research_navigator.data_plane.storage import DurableStorage, LocalStorage
from research_navigator.db import Database


class OfflineR2Storage:
    """R2-shaped storage double with the same key safety boundary."""

    def __init__(self, root: Path) -> None:
        self._storage = LocalStorage(root / "objects")

    def put(self, key: str, data: bytes) -> None:
        self._storage.put(key, data)

    def get(self, key: str) -> bytes:
        return self._storage.get(key)

    def delete(self, key: str) -> None:
        self._storage.delete(key)


def build_offline_database(provider_root: Path) -> Database:
    provider_root.mkdir(parents=True, exist_ok=True)
    return Database.from_url(f"sqlite+pysqlite:///{(provider_root / 'turso-double.db').as_posix()}")


def build_offline_storage(provider_root: Path) -> DurableStorage:
    return OfflineR2Storage(provider_root)
