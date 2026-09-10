from pathlib import Path

from cited_gap_fixture import add_cited_materials
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


def register(client: TestClient) -> dict[str, str]:
    auth = client.post(
        "/api/auth/register",
        json={
            "email": "worker-handlers@example.com",
            "password": "research-pass-123",
            "display_name": "Worker Handlers",
        },
    ).json()
    return {"Authorization": f"Bearer {auth['access_token']}"}


def test_worker_executes_analysis_recommendation_and_gap_challenge_handlers(
    tmp_path: Path,
) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        headers = register(client)
        client.put(
            "/api/research-profiles/me",
            headers=headers,
            json={
                "stage": "硕士一年级",
                "major": "大数据技术与工程",
                "broad_direction": "未来窗口异常风险排序",
                "keywords": ["future horizon", "alert ranking", "anomaly prediction"],
                "excluded_terms": [],
                "preferences": ["复现优先"],
                "compute_constraints": "单卡 GPU",
            },
        )
        project = client.post(
            "/api/projects",
            headers=headers,
            json={"name": "worker project", "broad_direction": "未来窗口异常风险排序"},
        ).json()
        papers = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "time series anomaly", "sources": ["fixture"], "limit": 3},
        ).json()["papers"]
        paper_ids = [paper["id"] for paper in papers]

        analysis_job = client.post(
            "/api/jobs",
            headers=headers,
            json={
                "job_type": "paper_analysis",
                "project_id": project["id"],
                "payload": {"paper_id": paper_ids[0], "project_id": project["id"]},
            },
        ).json()
        assert run_once(app.state.database, settings=settings) == analysis_job["id"]
        analysis_result = client.get(f"/api/jobs/{analysis_job['id']}", headers=headers).json()
        assert analysis_result["status"] == "succeeded"
        assert analysis_result["result"]["analysis_id"] > 0

        recommendation_job = client.post(
            "/api/jobs",
            headers=headers,
            json={
                "job_type": "recommendation_refresh",
                "project_id": project["id"],
                "payload": {"project_id": project["id"], "limit": 3},
            },
        ).json()
        assert run_once(app.state.database, settings=settings) == recommendation_job["id"]
        recommendation_result = client.get(
            f"/api/jobs/{recommendation_job['id']}", headers=headers
        ).json()
        assert recommendation_result["status"] == "succeeded"
        assert recommendation_result["result"]["recommendation_count"] == 3

        add_cited_materials(app, project["id"], paper_ids[:2])
        gap = client.post(
            "/api/gaps/generate",
            headers=headers,
            json={"project_id": project["id"], "paper_ids": paper_ids[:2]},
        ).json()
        challenge_job = client.post(
            "/api/jobs",
            headers=headers,
            json={
                "job_type": "gap_challenge",
                "project_id": project["id"],
                "payload": {"gap_id": gap["id"], "additional_terms": ["event-level warning"]},
            },
        ).json()
        assert run_once(app.state.database, settings=settings) == challenge_job["id"]
        challenge_result = client.get(f"/api/jobs/{challenge_job['id']}", headers=headers).json()
        assert challenge_result["status"] == "succeeded"
        assert challenge_result["result"]["gap_status"] == "pending_confirmation"
        assert challenge_result["result"]["challenge_query_count"] > 0


def test_worker_terminal_contract_records_order_attempts_and_failure(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        headers = register(client)
        success = client.post(
            "/api/jobs",
            headers=headers,
            json={"job_type": "noop", "payload": {"contract": "terminal"}},
        ).json()
        assert success["terminal"] is False
        assert run_once(app.state.database, settings=settings) == success["id"]
        success_read = client.get(f"/api/jobs/{success['id']}", headers=headers).json()
        assert success_read["status"] == "succeeded"
        assert success_read["terminal"] is True
        assert success_read["attempt_count"] == 1
        events = client.get(f"/api/jobs/{success['id']}/events", headers=headers).json()
        assert [event["event_type"] for event in events] == ["created", "started", "succeeded"]

        # Missing paper_id causes bounded retries. Pending after the first attempts is not PASS.
        failure = client.post(
            "/api/jobs",
            headers=headers,
            json={"job_type": "paper_analysis", "payload": {}},
        ).json()
        for attempt in range(1, failure["max_attempts"] + 1):
            assert run_once(app.state.database, settings=settings) == failure["id"]
            current = client.get(f"/api/jobs/{failure['id']}", headers=headers).json()
            assert current["attempt_count"] == attempt
            if attempt < failure["max_attempts"]:
                assert current["status"] == "pending"
                assert current["terminal"] is False
            else:
                assert current["status"] == "failed"
                assert current["terminal"] is True
                assert current["error"]
        failure_events = client.get(f"/api/jobs/{failure['id']}/events", headers=headers).json()
        event_types = [event["event_type"] for event in failure_events]
        assert event_types[0] == "created"
        assert event_types[-1] == "failed"
        assert event_types.count("started") == failure["max_attempts"]
        assert event_types.count("retry_scheduled") == failure["max_attempts"] - 1


def test_cancelled_job_is_terminal_and_never_claimed(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        headers = register(client)
        job = client.post(
            "/api/jobs", headers=headers, json={"job_type": "noop", "payload": {}}
        ).json()
        cancelled = client.post(f"/api/jobs/{job['id']}/cancel", headers=headers).json()
        assert cancelled["status"] == "cancelled"
        assert cancelled["terminal"] is True
        assert run_once(app.state.database, settings=settings) is None
        events = client.get(f"/api/jobs/{job['id']}/events", headers=headers).json()
        assert [event["event_type"] for event in events] == ["created", "cancelled"]
