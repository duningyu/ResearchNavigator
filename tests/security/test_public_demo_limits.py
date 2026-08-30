import json
from pathlib import Path

from fastapi.testclient import TestClient

from research_navigator.config import Settings
from research_navigator.main import create_app


def settings_for(tmp_path: Path, *, public_demo: bool) -> Settings:
    data_dir = tmp_path / ("demo" if public_demo else "local")
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
        public_demo_mode=public_demo,
        public_demo_max_users=1,
        public_demo_max_upload_mb=1,
        public_demo_max_active_jobs=1,
        public_demo_max_query_length=8,
        public_demo_max_job_payload_bytes=16,
    )


def register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "research-pass-123",
            "display_name": "Demo User",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_public_demo_enforces_bounded_resources(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path, public_demo=True))) as client:
        headers = register(client, "first@example.test")

        second_user = client.post(
            "/api/auth/register",
            json={
                "email": "second@example.test",
                "password": "research-pass-123",
                "display_name": "Second User",
            },
        )
        assert second_user.status_code == 429, second_user.text
        assert second_user.json()["detail"] == "PUBLIC_DEMO_USER_LIMIT_REACHED"

        long_query = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "ninechars", "limit": 1, "sources": ["fixture"]},
        )
        assert long_query.status_code == 422, long_query.text
        assert long_query.json()["detail"] == "PUBLIC_DEMO_QUERY_TOO_LONG"

        idempotent_headers = {**headers, "Idempotency-Key": "demo-job-1"}
        first_job = client.post(
            "/api/jobs", headers=idempotent_headers, json={"job_type": "noop", "payload": {}}
        )
        assert first_job.status_code == 201, first_job.text
        replayed_job = client.post(
            "/api/jobs", headers=idempotent_headers, json={"job_type": "noop", "payload": {}}
        )
        assert replayed_job.status_code == 201, replayed_job.text
        assert replayed_job.json()["id"] == first_job.json()["id"]
        second_job = client.post(
            "/api/jobs", headers=headers, json={"job_type": "noop", "payload": {}}
        )
        assert second_job.status_code == 429, second_job.text
        assert second_job.json()["detail"] == "PUBLIC_DEMO_ACTIVE_JOB_LIMIT_REACHED"

        oversized_payload = {"text": "x" * 32}
        assert len(json.dumps(oversized_payload, ensure_ascii=False).encode("utf-8")) > 16
        payload_job = client.post(
            "/api/jobs",
            headers=headers,
            json={"job_type": "noop", "payload": oversized_payload},
        )
        assert payload_job.status_code == 413, payload_job.text
        assert payload_job.json()["detail"] == "PUBLIC_DEMO_JOB_PAYLOAD_TOO_LARGE"

        paper = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "fixture", "limit": 1, "sources": ["fixture"]},
        )
        assert paper.status_code == 200, paper.text
        paper_id = paper.json()["papers"][0]["id"]
        upload = client.post(
            f"/api/papers/{paper_id}/upload",
            headers=headers,
            data={"rights_confirmed": "true"},
            files={
                "file": (
                    "oversized.pdf",
                    b"%PDF-1.4\n" + b"x" * (1024 * 1024),
                    "application/pdf",
                )
            },
        )
        assert upload.status_code == 400, upload.text
        assert "between 1 and 1048576 bytes" in upload.json()["detail"]


def test_normal_local_mode_ignores_public_demo_bounds(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path, public_demo=False))) as client:
        headers = register(client, "first@example.test")
        register(client, "second@example.test")

        search = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "time series anomaly", "limit": 1, "sources": ["fixture"]},
        )
        assert search.status_code == 200, search.text

        first_job = client.post(
            "/api/jobs", headers=headers, json={"job_type": "noop", "payload": {}}
        )
        second_job = client.post(
            "/api/jobs",
            headers=headers,
            json={"job_type": "noop", "payload": {"text": "x" * 32}},
        )
        assert first_job.status_code == 201, first_job.text
        assert second_job.status_code == 201, second_job.text
