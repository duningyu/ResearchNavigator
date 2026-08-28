from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.models import Paper


def settings_for(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "state"
    return Settings(
        data_dir=data_dir,
        database_url=f"sqlite+pysqlite:///{(data_dir / 'test.db').as_posix()}",
        upload_dir=data_dir / "uploads",
        vector_dir=data_dir / "vectors",
        backup_dir=data_dir / "backups",
        allowed_origins=("http://localhost:5173",),
        enable_fixture_source=False,
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
    data = client.post(
        "/api/auth/register",
        json={"email": email, "password": "research-pass-123", "display_name": "Cluster"},
    ).json()
    return {"Authorization": f"Bearer {data['access_token']}"}


def seed_papers(app) -> list[int]:
    rows = [
        ("TCN anomaly detection", ["time series", "anomaly detection"]),
        ("Convolutional industrial anomaly detection", ["time series", "anomaly detection"]),
        ("RAG for document question answering", ["retrieval", "language model"]),
    ]
    with app.state.database.session() as session:
        ids = []
        for title, concepts in rows:
            paper = Paper(
                title=title,
                normalized_title=title.casefold(),
                concepts_json=json.dumps(concepts),
                fields_of_study_json="[]",
                keywords_json="[]",
            )
            session.add(paper)
            session.flush()
            ids.append(paper.id)
        session.commit()
        return ids


def test_direction_cluster_api_is_versioned_deterministic_and_user_scoped(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        owner = register(client, "cluster-owner@example.com")
        other = register(client, "cluster-other@example.com")
        project_id = client.post(
            "/api/projects", headers=owner, json={"name": "Direction Map"}
        ).json()["id"]
        paper_ids = seed_papers(app)
        first = client.post(
            f"/api/projects/{project_id}/direction-clusters",
            headers=owner,
            json={"paper_ids": paper_ids, "threshold": 0.2},
        )
        assert first.status_code == 201, first.text
        body = first.json()
        assert body["algorithm_version"] == "direction-cluster-v1"
        assert body["input_hash"]
        assert "not an objective field taxonomy" in body["disclaimer"]
        assert len(body["members"]) == 3
        assert any(item["is_unclustered"] for item in body["members"])
        assert client.get(f"/api/direction-clusters/{body['id']}", headers=other).status_code == 404

        repeated = client.post(
            f"/api/projects/{project_id}/direction-clusters",
            headers=owner,
            json={"paper_ids": list(reversed(paper_ids)), "threshold": 0.2},
        ).json()
        assert repeated["input_hash"] == body["input_hash"]
        first_members = [
            (x["paper_id"], x["cluster_key"], x["is_unclustered"]) for x in body["members"]
        ]
        second_members = [
            (x["paper_id"], x["cluster_key"], x["is_unclustered"]) for x in repeated["members"]
        ]
        assert first_members == second_members
