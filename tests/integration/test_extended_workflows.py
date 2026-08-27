from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from reportlab.pdfgen.canvas import Canvas

from research_navigator.config import Settings
from research_navigator.main import create_app


def make_settings(tmp_path: Path) -> Settings:
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
        json={"email": email, "password": "research-pass-123", "display_name": email},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def search_fixture(
    client: TestClient, headers: dict[str, str], query: str = "time series anomaly", limit: int = 4
) -> dict[str, object]:
    response = client.post(
        "/api/search/papers",
        headers=headers,
        json={"query": query, "sources": ["fixture"], "limit": limit},
    )
    assert response.status_code == 200, response.text
    return response.json()


def make_pdf() -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(72, 760, "Abstract")
    canvas.drawString(72, 735, "A local authorized document for deletion testing.")
    canvas.save()
    return buffer.getvalue()


def test_search_session_can_be_rerun_and_paper_can_be_resolved_and_related(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        headers = register(client, "extended-search@example.com")
        initial = search_fixture(client, headers)
        session_id = initial["session_id"]
        paper = initial["papers"][0]

        rerun = client.post(f"/api/search/sessions/{session_id}/rerun", headers=headers)
        assert rerun.status_code == 200, rerun.text
        assert rerun.json()["session_id"] != session_id
        assert rerun.json()["result_count"] == initial["result_count"]

        resolved = client.post(
            "/api/papers/resolve",
            headers=headers,
            json={"title": paper["title"], "publication_year": paper["publication_year"]},
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["id"] == paper["id"]

        related = client.get(f"/api/papers/{paper['id']}/related?limit=3", headers=headers)
        assert related.status_code == 200, related.text
        assert all(item["paper"]["id"] != paper["id"] for item in related.json())
        assert related.json()[0]["score"] >= related.json()[-1]["score"]
        assert related.json()[0]["rationale"]


def test_recommendations_are_refreshable_explainable_and_persisted(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        headers = register(client, "recommend@example.com")
        client.put(
            "/api/research-profiles/me",
            headers=headers,
            json={
                "stage": "硕士一年级",
                "major": "大数据技术与工程",
                "broad_direction": "多变量时序异常预测",
                "keywords": ["future horizon", "alert ranking", "anomaly prediction"],
                "excluded_terms": [],
                "preferences": ["复现优先"],
                "compute_constraints": "单卡 GPU",
            },
        )
        project = client.post(
            "/api/projects",
            headers=headers,
            json={"name": "recommendation project", "broad_direction": "异常预测"},
        ).json()
        search_fixture(client, headers, limit=5)

        refreshed = client.post(
            "/api/recommendations/refresh",
            headers=headers,
            json={"project_id": project["id"], "limit": 5},
        )
        assert refreshed.status_code == 200, refreshed.text
        records = refreshed.json()
        assert records
        assert all(record["reason"] for record in records)
        assert all(0.0 <= record["score"] <= 1.0 for record in records)
        assert all(record["evidence"]["rule_version"] == "recommendation-v1" for record in records)
        assert any(
            record["category"] in {"入门综述", "高相关近期论文", "最适合复现"} for record in records
        )

        persisted = client.get(f"/api/recommendations?project_id={project['id']}", headers=headers)
        assert persisted.status_code == 200
        assert [row["id"] for row in persisted.json()] == [row["id"] for row in records]


def test_uploaded_document_can_only_be_deleted_by_owner_and_file_is_removed(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        owner = register(client, "document-owner@example.com")
        other = register(client, "document-other@example.com")
        paper_id = search_fixture(client, owner, limit=1)["papers"][0]["id"]
        uploaded = client.post(
            f"/api/papers/{paper_id}/upload",
            headers=owner,
            data={"rights_confirmed": "true"},
            files={"file": ("authorized.pdf", make_pdf(), "application/pdf")},
        )
        assert uploaded.status_code == 201, uploaded.text
        document_id = uploaded.json()["id"]
        stored_files = list((tmp_path / "state" / "uploads").rglob("*.pdf"))
        assert len(stored_files) == 1

        denied = client.delete(f"/api/documents/{document_id}", headers=other)
        assert denied.status_code == 404
        assert stored_files[0].exists()

        deleted = client.delete(f"/api/documents/{document_id}", headers=owner)
        assert deleted.status_code == 204, deleted.text
        assert not stored_files[0].exists()
        status = client.get(f"/api/papers/{paper_id}/content-status", headers=owner)
        assert status.json()["documents"] == []


def test_workspace_export_is_user_scoped_and_omits_credentials(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        first = register(client, "export-first@example.com")
        second = register(client, "export-second@example.com")
        first_project = client.post(
            "/api/projects", headers=first, json={"name": "first private project"}
        ).json()
        client.post("/api/projects", headers=second, json={"name": "second private project"})
        paper_id = search_fixture(client, first, limit=1)["papers"][0]["id"]
        client.post("/api/library/favorites", headers=first, json={"paper_id": paper_id})

        exported = client.get("/api/workspace/export", headers=first)
        assert exported.status_code == 200, exported.text
        payload = exported.json()
        assert payload["format_version"] == 1
        assert payload["user"]["email"] == "export-first@example.com"
        assert payload["projects"][0]["id"] == first_project["id"]
        assert all(project["name"] != "second private project" for project in payload["projects"])
        serialized = exported.text.lower()
        assert "password_hash" not in serialized
        assert "session_tokens" not in serialized
