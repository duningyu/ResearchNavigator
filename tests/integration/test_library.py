from pathlib import Path

from fastapi.testclient import TestClient

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
    payload = client.post(
        "/api/auth/register",
        json={"email": email, "password": "research-pass-123", "display_name": email},
    ).json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


def fixture_paper(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        "/api/search/papers",
        headers=headers,
        json={"query": "anomaly detection", "sources": ["fixture"], "limit": 1},
    )
    return response.json()["papers"][0]["id"]


def test_library_favorite_note_tag_and_reading_status_persist(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        first = register(client, "library-a@example.com")
        second = register(client, "library-b@example.com")
        paper_id = fixture_paper(client, first)

        favorite = client.post("/api/library/favorites", headers=first, json={"paper_id": paper_id})
        assert favorite.status_code == 201

        note = client.post(
            "/api/library/notes",
            headers=first,
            json={"paper_id": paper_id, "content": "重点检查未来窗口标签是否因果。"},
        )
        assert note.status_code == 201
        note_id = note.json()["id"]

        status = client.put(
            f"/api/library/papers/{paper_id}/reading-status",
            headers=first,
            json={"status": "reading", "progress": 35},
        )
        assert status.status_code == 200
        assert status.json()["progress"] == 35

        tag = client.post("/api/library/tags", headers=first, json={"name": "异常预测"})
        assert tag.status_code == 201
        tag_id = tag.json()["id"]
        assert (
            client.post(f"/api/library/papers/{paper_id}/tags/{tag_id}", headers=first).status_code
            == 204
        )

        library = client.get("/api/library", headers=first)
        assert library.status_code == 200
        item = library.json()["items"][0]
        assert item["paper"]["id"] == paper_id
        assert item["favorite"] is True
        assert item["notes"][0]["id"] == note_id
        assert item["reading_status"]["status"] == "reading"
        assert item["tags"][0]["name"] == "异常预测"

        other_library = client.get("/api/library", headers=second)
        assert other_library.status_code == 200
        assert other_library.json()["items"] == []
        assert (
            client.put(
                f"/api/library/notes/{note_id}",
                headers=second,
                json={"content": "unauthorized edit"},
            ).status_code
            == 404
        )

        assert client.delete(f"/api/library/favorites/{paper_id}", headers=first).status_code == 204
