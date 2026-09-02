from pathlib import Path

import pytest

from research_navigator.data_plane.database import database_dialect, redact_database_url
from research_navigator.data_plane.storage import (
    Boto3R2Transport,
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


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        from io import BytesIO

        return {"Body": BytesIO(self.objects[(Bucket, Key)])}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, int]:
        return {"ContentLength": len(self.objects[(Bucket, Key)])}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)


def test_boto3_r2_transport_and_stat() -> None:
    transport = Boto3R2Transport(FakeS3Client())
    storage = R2Storage(bucket="rn223", transport=transport)
    storage.put("users/7/doc.pdf", b"pdf")
    assert storage.get("users/7/doc.pdf") == b"pdf"
    assert storage.stat("users/7/doc.pdf") == {"ContentLength": 3}
    storage.delete("users/7/doc.pdf")


def test_r2_settings_are_fail_closed_and_secret_repr_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    from research_navigator.config import Settings

    monkeypatch.setenv("RN_STORAGE_BACKEND", "r2")
    monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
    with pytest.raises(ValueError, match="R2 credentials"):
        Settings.from_env()

    monkeypatch.setenv("R2_ACCESS_KEY_ID", "access-id")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret-value")
    monkeypatch.setenv("R2_ACCOUNT_ID", "account")
    monkeypatch.setenv("R2_BUCKET", "rn223")
    settings = Settings.from_env()
    assert "secret-value" not in repr(settings)
    assert settings.r2_region == "auto"


def test_runtime_storage_builder_selects_r2_without_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import boto3

    from research_navigator.config import Settings
    from research_navigator.data_plane.storage import build_runtime_storage

    settings = Settings(
        data_dir=tmp_path,
        database_url="sqlite+pysqlite:///runtime.db",
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        backup_dir=tmp_path / "backups",
        allowed_origins=(),
        enable_fixture_source=True,
        enable_openalex=False,
        enable_crossref=False,
        enable_arxiv=False,
        enable_semantic_scholar=False,
        semantic_scholar_api_key=None,
        unpaywall_email=None,
        crossref_mailto=None,
        llm_base_url=None,
        llm_api_key=None,
        llm_model=None,
        max_pdf_bytes=1024,
        session_ttl_hours=1,
        environment="test",
        storage_backend="r2",
        r2_bucket="researchnav-documents",
        r2_account_id="a" * 32,
        r2_access_key_id="access-id",
        r2_secret_access_key="secret-value",
    )
    fake_client = FakeS3Client()
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: fake_client)

    storage = build_runtime_storage(settings)

    assert isinstance(storage, R2Storage)
    storage.put("rn223-validation/test/object.bin", b"ok")
    assert storage.get("rn223-validation/test/object.bin") == b"ok"
