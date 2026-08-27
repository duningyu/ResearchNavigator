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


def register(client: TestClient, email: str) -> dict[str, str]:
    auth = client.post(
        "/api/auth/register",
        json={"email": email, "password": "research-pass-123", "display_name": email},
    ).json()
    return {"Authorization": f"Bearer {auth['access_token']}"}


def setup_compare(client: TestClient, headers: dict[str, str]) -> tuple[int, int]:
    client.put(
        "/api/research-profiles/me",
        headers=headers,
        json={
            "stage": "硕士",
            "major": "大数据",
            "broad_direction": "未来窗口异常风险排序",
            "keywords": ["future window", "time series", "risk ranking"],
            "excluded_terms": [],
            "preferences": ["evidence-first"],
            "compute_constraints": "single GPU",
        },
    )
    project = client.post(
        "/api/projects",
        headers=headers,
        json={"name": "Direction", "broad_direction": "未来窗口异常风险排序"},
    ).json()
    papers = client.post(
        "/api/search/papers",
        headers=headers,
        json={"query": "anomaly detection", "sources": ["fixture"], "limit": 2},
    ).json()["papers"]
    ids = [paper["id"] for paper in papers]
    for paper_id in ids:
        response = client.post(
            f"/api/papers/{paper_id}/analyze",
            headers=headers,
            json={"project_id": project["id"]},
        )
        assert response.status_code == 200, response.text
    paper_set = client.post(
        "/api/paper-sets",
        headers=headers,
        json={
            "project_id": project["id"],
            "purpose": "compare",
            "name": "Selected papers",
            "paper_ids": ids,
            "source_kind": "explicit",
        },
    ).json()
    return project["id"], paper_set["id"]


def test_comparison_uses_explicit_set_and_deep_evidence_rows(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        headers = register(client, "compare@example.com")
        project_id, paper_set_id = setup_compare(client, headers)

        response = client.post(
            "/api/comparisons",
            headers=headers,
            json={"project_id": project_id, "paper_set_id": paper_set_id},
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["paper_set_id"] == paper_set_id
        assert payload["direction_snapshot"]["project"]["broad_direction"] == "未来窗口异常风险排序"
        assert len(payload["papers"]) == 2
        rows = {row["key"]: row for row in payload["rows"]}
        for key in (
            "research_problem",
            "task_definition",
            "core_methods",
            "method_innovation",
            "theoretical_contribution",
            "research_route",
            "datasets",
            "metrics",
            "experimental_protocol",
            "future_work_explicit",
            "limitations_author_stated",
            "direction_relevance",
        ):
            assert key in rows
            assert len(rows[key]["cells"]) == 2
            assert all("evidence_state" in cell for cell in rows[key]["cells"])
            assert all("citations" in cell for cell in rows[key]["cells"])
        relevance = rows["direction_relevance"]["cells"][0]["value"]
        assert "score" in relevance
        assert "components" in relevance
        assert "reasons" in relevance
        assert payload["evidence_hash"]

        stored = client.get(f"/api/comparisons/{payload['id']}", headers=headers)
        assert stored.status_code == 200
        assert stored.json()["evidence_hash"] == payload["evidence_hash"]


def test_comparison_requires_two_papers_and_is_user_scoped(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        owner = register(client, "compare-owner@example.com")
        other = register(client, "compare-other@example.com")
        project_id, paper_set_id = setup_compare(client, owner)
        comparison = client.post(
            "/api/comparisons",
            headers=owner,
            json={"project_id": project_id, "paper_set_id": paper_set_id},
        ).json()
        denied = client.get(f"/api/comparisons/{comparison['id']}", headers=other)
        assert denied.status_code == 404

        papers = client.get(f"/api/paper-sets/{paper_set_id}", headers=owner).json()["paper_ids"]
        single = client.post(
            "/api/paper-sets",
            headers=owner,
            json={
                "project_id": project_id,
                "purpose": "compare",
                "name": "Single",
                "paper_ids": [papers[0]],
                "source_kind": "explicit",
            },
        ).json()
        invalid = client.post(
            "/api/comparisons",
            headers=owner,
            json={"project_id": project_id, "paper_set_id": single["id"]},
        )
        assert invalid.status_code == 422
