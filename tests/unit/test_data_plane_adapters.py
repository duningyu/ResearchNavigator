from pathlib import Path

import pytest

from research_navigator.data_plane.database import database_dialect, redact_database_url
from research_navigator.data_plane.storage import (
    LocalStorage,
    R2Storage,
    StorageKeyError,
    build_storage,
)


def test_database_dialect_contract_and_redaction() -> None:
    assert database_dialect("sqlite+pysqlite:///runtime/db.sqlite").supports_sqlite_fts
    dialect = database_dialect("postgresql+psycopg://alice:secret@example/db")
    assert dialect.name == "postgresql"
    assert dialect.supports_postgres_text_search is True
    safe = redact_database_url("postgresql+psycopg://alice:secret@example/db")
    assert "secret" not in safe
    with pytest.raises(ValueError):
        database_dialect("mysql+pymysql://x:y@host/db")


def test_local_storage_is_user_scoped_and_traversal_safe(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    storage.put("users/1/doc.pdf", b"pdf")
    assert storage.get("users/1/doc.pdf") == b"pdf"
    with pytest.raises(StorageKeyError):
        storage.put("users/1/../../2/leak", b"x")
    assert not (tmp_path.parent / "2" / "leak").exists()


class FakeTransport:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, bucket: str, key: str, data: bytes) -> None:
        self.objects[(bucket, key)] = data

    def get_object(self, *, bucket: str, key: str) -> bytes:
        return self.objects[(bucket, key)]

    def delete_object(self, *, bucket: str, key: str) -> None:
        self.objects.pop((bucket, key), None)


def test_r2_adapter_uses_only_transport_calls() -> None:
    transport = FakeTransport()
    storage = R2Storage(bucket="rn223", transport=transport)
    storage.put("users/7/doc.pdf", b"pdf")
    assert storage.get("users/7/doc.pdf") == b"pdf"
    storage.delete("users/7/doc.pdf")
    assert transport.objects == {}


def test_local_backend_does_not_require_r2_configuration(tmp_path: Path) -> None:
    assert isinstance(build_storage(backend="local", local_root=tmp_path), LocalStorage)
