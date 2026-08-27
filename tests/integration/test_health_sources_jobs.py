from pathlib import Path

from fastapi.testclient import TestClient
from services.worker.main import run_once

from research_navigator.config import Settings
from research_navigator.main import create_app


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


def authenticate(client: TestClient) -> dict[str, str]:
    auth = client.post(
        "/api/auth/register",
        json={
            "email": "jobs@example.com",
            "password": "research-pass-123",
            "display_name": "Jobs User",
        },
    ).json()
    return {"Authorization": f"Bearer {auth['access_token']}"}


def test_health_source_status_and_persistent_job_lifecycle(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["database"] == "ok"
        headers = authenticate(client)

        sources = client.get("/api/sources/status", headers=headers)
        assert sources.status_code == 200
        status_by_name = {item["name"]: item for item in sources.json()}
        assert status_by_name["fixture"]["status"] == "ok"
        assert status_by_name["openalex"]["status"] == "disabled"
        tested = client.post("/api/sources/fixture/test", headers=headers)
        assert tested.status_code == 200
        assert tested.json()["status"] == "ok"

        created = client.post(
            "/api/jobs",
            headers=headers,
            json={"job_type": "noop", "payload": {"value": 7}},
        )
        assert created.status_code == 201, created.text
        job = created.json()
        assert job["status"] == "pending"

        processed = run_once(app.state.database)
        assert processed == job["id"]
        stored = client.get(f"/api/jobs/{job['id']}", headers=headers)
        assert stored.json()["status"] == "succeeded"
        assert stored.json()["result"] == {"echo": {"value": 7}}
        events = client.get(f"/api/jobs/{job['id']}/events", headers=headers).json()
        assert [event["event_type"] for event in events] >= ["created", "started", "succeeded"]

        pending = client.post(
            "/api/jobs", headers=headers, json={"job_type": "noop", "payload": {}}
        ).json()
        cancelled = client.post(f"/api/jobs/{pending['id']}/cancel", headers=headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"


def test_jobs_list_is_user_scoped_and_terminal_state_is_explicit(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = authenticate(client)
        created = client.post(
            "/api/jobs", headers=headers, json={"job_type": "noop", "payload": {"x": 1}}
        ).json()
        listed = client.get("/api/jobs", headers=headers)
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()] == [created["id"]]
        assert listed.json()[0]["terminal"] is False
        run_once(app.state.database)
        finished = client.get(f"/api/jobs/{created['id']}", headers=headers).json()
        assert finished["status"] == "succeeded"
        assert finished["terminal"] is True
        assert finished["finished_at"] is not None


def test_partial_evidence_job_is_terminal_in_generic_job_api(tmp_path: Path) -> None:
    import json

    from research_navigator.models import Job

    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = authenticate(client)
        with app.state.database.session() as session:
            user_id = int(client.get("/api/auth/me", headers=headers).json()["id"])
            row = Job(
                user_id=user_id,
                project_id=None,
                job_type="evidence_workflow_v1",
                status="partial",
                payload_json=json.dumps({"paper_id": 1}),
                result_json=json.dumps({"warnings": ["OpenAlex rate limited"]}),
                max_attempts=3,
                attempt_count=1,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            job_id = row.id

        response = client.get(f"/api/jobs/{job_id}", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "partial"
        assert response.json()["terminal"] is True
