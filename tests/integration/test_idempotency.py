from pathlib import Path

from fastapi.testclient import TestClient

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


def auth(client: TestClient) -> dict[str, str]:
    row = client.post(
        "/api/auth/register",
        json={"email": "idem@example.com", "password": "research-pass-123", "display_name": "Idem"},
    ).json()
    return {"Authorization": f"Bearer {row['access_token']}"}


def idem(headers: dict[str, str], key: str) -> dict[str, str]:
    return {**headers, "Idempotency-Key": key, "X-Scenario-Version": "feedback-closure-v1"}


def test_mutation_replay_returns_same_resources_without_duplicates(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        headers = auth(client)
        project_payload = {"name": "Idempotent project", "broad_direction": "anomaly detection"}
        first_project = client.post(
            "/api/projects", headers=idem(headers, "project-1"), json=project_payload
        )
        second_project = client.post(
            "/api/projects", headers=idem(headers, "project-1"), json=project_payload
        )
        assert first_project.status_code == second_project.status_code == 201
        assert first_project.json()["id"] == second_project.json()["id"]
        project_id = first_project.json()["id"]

        papers = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "anomaly detection", "sources": ["fixture"], "limit": 2},
        ).json()["papers"]
        paper_ids = [paper["id"] for paper in papers]

        favorite_payload = {"paper_id": paper_ids[0]}
        fav1 = client.post(
            "/api/library/favorites", headers=idem(headers, "fav-1"), json=favorite_payload
        )
        fav2 = client.post(
            "/api/library/favorites", headers=idem(headers, "fav-1"), json=favorite_payload
        )
        assert fav1.json()["id"] == fav2.json()["id"]

        tag1 = client.post(
            "/api/library/tags", headers=idem(headers, "tag-1"), json={"name": "critical"}
        )
        tag2 = client.post(
            "/api/library/tags", headers=idem(headers, "tag-1"), json={"name": "critical"}
        )
        assert tag1.json()["id"] == tag2.json()["id"]

        note_payload = {"paper_id": paper_ids[0], "content": "same note"}
        note1 = client.post(
            "/api/library/notes", headers=idem(headers, "note-1"), json=note_payload
        )
        note2 = client.post(
            "/api/library/notes", headers=idem(headers, "note-1"), json=note_payload
        )
        assert note1.json()["id"] == note2.json()["id"]

        set_payload = {
            "project_id": project_id,
            "purpose": "gap",
            "name": "Idem set",
            "paper_ids": paper_ids,
            "source_kind": "explicit",
        }
        set1 = client.post("/api/paper-sets", headers=idem(headers, "set-1"), json=set_payload)
        set2 = client.post("/api/paper-sets", headers=idem(headers, "set-1"), json=set_payload)
        assert set1.json()["id"] == set2.json()["id"]

        gap_payload = {"project_id": project_id, "paper_set_id": set1.json()["id"]}
        gap1 = client.post("/api/gaps/generate", headers=idem(headers, "gap-1"), json=gap_payload)
        gap2 = client.post("/api/gaps/generate", headers=idem(headers, "gap-1"), json=gap_payload)
        assert gap1.json()["id"] == gap2.json()["id"]
        gap_id = gap1.json()["id"]
        client.post(f"/api/gaps/{gap_id}/challenge", headers=headers, json={})
        client.post(
            f"/api/gaps/{gap_id}/confirm",
            headers=headers,
            json={"confirmed": True, "note": "human"},
        )

        plan_payload = {"project_id": project_id, "gap_id": gap_id}
        plan1 = client.post("/api/plans", headers=idem(headers, "plan-1"), json=plan_payload)
        plan2 = client.post("/api/plans", headers=idem(headers, "plan-1"), json=plan_payload)
        assert plan1.json()["id"] == plan2.json()["id"]

        job_payload = {"job_type": "noop", "payload": {"value": 7}, "project_id": project_id}
        job1 = client.post("/api/jobs", headers=idem(headers, "job-1"), json=job_payload)
        job2 = client.post("/api/jobs", headers=idem(headers, "job-1"), json=job_payload)
        assert job1.json()["id"] == job2.json()["id"]

        assert len(client.get("/api/projects", headers=headers).json()) == 1
        library = client.get("/api/library", headers=headers).json()["items"]
        assert (
            len(
                [
                    note
                    for item in library
                    for note in item["notes"]
                    if note["content"] == "same note"
                ]
            )
            == 1
        )
        assert len(client.get("/api/paper-sets", headers=headers).json()) == 1
        assert len(client.get("/api/gaps", headers=headers).json()) == 1
        assert len(client.get("/api/plans", headers=headers).json()) == 1
        assert len(client.get("/api/jobs", headers=headers).json()) == 1


def test_reusing_idempotency_key_with_different_payload_is_rejected(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        headers = auth(client)
        first = client.post(
            "/api/projects",
            headers=idem(headers, "same-key"),
            json={"name": "First"},
        )
        assert first.status_code == 201
        conflict = client.post(
            "/api/projects",
            headers=idem(headers, "same-key"),
            json={"name": "Different"},
        )
        assert conflict.status_code == 409
