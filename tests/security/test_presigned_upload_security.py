from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from research_navigator.config import Settings
from research_navigator.data_plane.storage import R2Storage
from research_navigator.documents.security import DocumentSecurityError
from research_navigator.main import create_app
from research_navigator.uploads import (
    MAX_PRESIGN_TTL_SECONDS,
    PRESIGN_TTL_SECONDS,
    issue_completion_token,
    redact_presigned_url,
    validate_completion_token_bucket,
    validate_presign_metadata,
    validated_r2_bucket,
    verify_completion_token,
)


def settings_for(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "state"
    return Settings(
        data_dir=data_dir,
        database_url=f"sqlite+pysqlite:///{(data_dir / 'test.db').as_posix()}",
        upload_dir=data_dir / "uploads",
        vector_dir=data_dir / "vectors",
        backup_dir=data_dir / "backups",
        allowed_origins=("http://localhost:5173",),
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
        max_pdf_bytes=2_000_000,
        session_ttl_hours=24,
        environment="test",
    )


def register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "research-pass-123", "display_name": "Upload User"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_presign_requires_authentication(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        response = client.post(
            "/api/papers/1/uploads/presign",
            json={
                "filename": "paper.pdf",
                "content_type": "application/pdf",
                "size_bytes": 128,
                "sha256": "a" * 64,
            },
        )
    assert response.status_code == 401


def test_local_storage_does_not_expose_presign_endpoint(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        headers = register(client, "presign-local@example.test")
        response = client.post(
            "/api/papers/999/uploads/presign",
            headers=headers,
            json={
                "filename": "paper.pdf",
                "content_type": "application/pdf",
                "size_bytes": 128,
                "sha256": "a" * 64,
            },
        )
    assert response.status_code in {409, 503}


@pytest.mark.parametrize(
    ("filename", "content_type", "size_bytes", "sha256"),
    [
        ("paper.txt", "application/pdf", 128, "a" * 64),
        ("paper.pdf", "text/plain", 128, "a" * 64),
        ("paper.pdf", "application/pdf", 0, "a" * 64),
        ("paper.pdf", "application/pdf", 128, "not-a-sha"),
    ],
)
def test_presign_metadata_rejects_invalid_claims(
    filename: str, content_type: str, size_bytes: int, sha256: str
) -> None:
    with pytest.raises(DocumentSecurityError):
        validate_presign_metadata(
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            max_bytes=1024,
        )


def test_presign_metadata_rejects_oversize_and_accepts_supported_pdf() -> None:
    with pytest.raises(DocumentSecurityError):
        validate_presign_metadata(
            filename="paper.pdf",
            content_type="application/pdf",
            size_bytes=1025,
            sha256="a" * 64,
            max_bytes=1024,
        )
    metadata = validate_presign_metadata(
        filename="paper.pdf",
        content_type=" application/x-pdf ",
        size_bytes=128,
        sha256="A" * 64,
        max_bytes=1024,
    )
    assert metadata.content_type == "application/x-pdf"
    assert metadata.sha256 == "a" * 64


def test_completion_token_is_user_bound_tamper_evident_and_expiring() -> None:
    token = issue_completion_token(
        secret="unit-test-secret",
        claims={"user_id": 7, "paper_id": 8, "key": "uploads/7/random/a.pdf"},
        now=100,
    )
    assert verify_completion_token(secret="unit-test-secret", token=token, now=100)["user_id"] == 7
    with pytest.raises(DocumentSecurityError):
        verify_completion_token(secret="wrong-secret", token=token, now=100)
    with pytest.raises(DocumentSecurityError):
        verify_completion_token(secret="unit-test-secret", token=token, now=401)


def test_presigned_url_redaction_drops_query_credentials() -> None:
    safe = redact_presigned_url(
        "https://r2.example/upload.pdf?X-Amz-Credential=secret&X-Amz-Signature=secret"
    )
    assert safe == "https://r2.example/upload.pdf"
    assert "Amz" not in safe


def test_security_contract_constants_are_bounded_and_bucket_fixed() -> None:
    assert PRESIGN_TTL_SECONDS == 300
    assert PRESIGN_TTL_SECONDS <= MAX_PRESIGN_TTL_SECONDS <= 600


class PresignTransport:
    def put_object(self, *, bucket: str, key: str, data: bytes) -> None: ...

    def get_object(self, *, bucket: str, key: str) -> bytes:
        return b""

    def delete_object(self, *, bucket: str, key: str) -> None: ...


def r2_settings(tmp_path: Path, bucket: str | None) -> Settings:
    return replace(
        settings_for(tmp_path),
        storage_backend="r2",
        r2_bucket=bucket,
    )


def test_preview_bucket_is_accepted_when_settings_and_storage_match(tmp_path: Path) -> None:
    settings = r2_settings(tmp_path, "researchnavigator-r3-preview")
    storage = R2Storage(bucket="researchnavigator-r3-preview", transport=PresignTransport())

    assert validated_r2_bucket(settings=settings, storage=storage) == "researchnavigator-r3-preview"


def test_settings_and_storage_bucket_mismatch_is_rejected_safely(tmp_path: Path) -> None:
    settings = r2_settings(tmp_path, "researchnavigator-r3-preview")
    storage = R2Storage(bucket="researchnav-documents", transport=PresignTransport())

    with pytest.raises(DocumentSecurityError, match="does not match current environment"):
        validated_r2_bucket(settings=settings, storage=storage)


def test_completion_token_contains_configured_bucket_claim() -> None:
    token = issue_completion_token(
        secret="unit-test-secret",
        claims={"user_id": 7, "paper_id": 8, "bucket": "researchnavigator-r3-preview"},
        now=100,
    )

    claims = verify_completion_token(secret="unit-test-secret", token=token, now=100)
    assert claims["bucket"] == "researchnavigator-r3-preview"


def test_completion_token_from_other_bucket_is_rejected(tmp_path: Path) -> None:
    settings = r2_settings(tmp_path, "researchnav-documents")
    storage = R2Storage(bucket="researchnav-documents", transport=PresignTransport())

    with pytest.raises(DocumentSecurityError, match="does not match current environment"):
        validate_completion_token_bucket(
            settings=settings,
            storage=storage,
            claim_bucket="researchnavigator-r3-preview",
        )


def test_missing_configured_bucket_fails_closed(tmp_path: Path) -> None:
    settings = r2_settings(tmp_path, None)
    storage = R2Storage(bucket="researchnav-documents", transport=PresignTransport())

    with pytest.raises(DocumentSecurityError, match="does not match current environment"):
        validated_r2_bucket(settings=settings, storage=storage)
