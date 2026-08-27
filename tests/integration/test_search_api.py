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


def test_fixture_search_persists_session_and_paper_provenance(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        registered = client.post(
            "/api/auth/register",
            json={
                "email": "search@example.com",
                "password": "research-pass-123",
                "display_name": "Search User",
            },
        ).json()
        headers = {"Authorization": f"Bearer {registered['access_token']}"}

        response = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "time series anomaly", "limit": 5, "sources": ["fixture"]},
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["result_count"] >= 2
        assert payload["source_status"]["fixture"]["status"] == "ok"
        assert all(item["is_fixture"] is True for item in payload["papers"])
        assert all(item["source_provenance"] for item in payload["papers"])

        sessions = client.get("/api/search/sessions", headers=headers)
        assert sessions.status_code == 200
        assert sessions.json()[0]["query"] == "time series anomaly"

        paper_id = payload["papers"][0]["id"]
        detail = client.get(f"/api/papers/{paper_id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["id"] == paper_id
        assert detail.json()["source_provenance"][0]["source"] == "fixture"


def test_discovery_search_persists_mode_seed_composition_and_session_papers(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        registered = client.post(
            "/api/auth/register",
            json={
                "email": "discovery@example.com",
                "password": "research-pass-123",
                "display_name": "Discovery",
            },
        ).json()
        headers = {"Authorization": f"Bearer {registered['access_token']}"}

        first = client.post(
            "/api/search/papers",
            headers=headers,
            json={
                "query": "anomaly detection",
                "limit": 50,
                "sources": ["fixture"],
                "mode": "auto",
            },
        )
        assert first.status_code == 200, first.text
        payload = first.json()
        assert payload["search_mode"] == "discovery"
        assert payload["diversity_seed"]
        assert payload["ranking_rule_version"] == "discovery-ranking-v1"
        assert payload["composition"]["requested_limit"] == 50
        assert all("ranking" in paper and paper["ranking"] for paper in payload["papers"])

        session = client.get(f"/api/search/sessions/{payload['session_id']}", headers=headers)
        assert session.status_code == 200
        assert session.json()["diversity_seed"] == payload["diversity_seed"]
        assert session.json()["search_mode"] == "discovery"

        corpus = client.get(f"/api/search/sessions/{payload['session_id']}/papers", headers=headers)
        assert corpus.status_code == 200
        assert [item["id"] for item in corpus.json()] == [item["id"] for item in payload["papers"]]

        rerun = client.post(f"/api/search/sessions/{payload['session_id']}/rerun", headers=headers)
        assert rerun.status_code == 200
        assert rerun.json()["diversity_seed"] == payload["diversity_seed"]

        new_search = client.post(
            "/api/search/papers",
            headers=headers,
            json={
                "query": "anomaly detection",
                "limit": 50,
                "sources": ["fixture"],
                "mode": "auto",
            },
        )
        assert new_search.status_code == 200
        assert new_search.json()["diversity_seed"] != payload["diversity_seed"]


def test_search_session_papers_are_user_scoped(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        first = client.post(
            "/api/auth/register",
            json={
                "email": "session-a@example.com",
                "password": "research-pass-123",
                "display_name": "A",
            },
        ).json()
        second = client.post(
            "/api/auth/register",
            json={
                "email": "session-b@example.com",
                "password": "research-pass-123",
                "display_name": "B",
            },
        ).json()
        first_headers = {"Authorization": f"Bearer {first['access_token']}"}
        second_headers = {"Authorization": f"Bearer {second['access_token']}"}
        search = client.post(
            "/api/search/papers",
            headers=first_headers,
            json={"query": "attention", "limit": 10, "sources": ["fixture"], "mode": "auto"},
        ).json()
        denied = client.get(
            f"/api/search/sessions/{search['session_id']}/papers", headers=second_headers
        )
        assert denied.status_code == 404
