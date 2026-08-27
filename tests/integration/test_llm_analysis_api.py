from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from research_navigator.analysis.providers import DeterministicMockProvider
from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.models import AgentRun, PaperAnalysisRecord, ToolCall


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
        llm_base_url="https://llm.example/v1",
        llm_api_key="never-persist-this-secret",
        llm_model="audit-model",
        max_pdf_bytes=2_000_000,
        session_ttl_hours=24,
        environment="test",
        analysis_provider="openai_compatible",
    )


def register(client: TestClient) -> dict[str, str]:
    data = client.post(
        "/api/auth/register",
        json={"email": "llm-api@example.com", "password": "research-pass-123", "display_name": "LLM"},
    ).json()
    return {"Authorization": f"Bearer {data['access_token']}"}


def paper_id(client: TestClient, headers: dict[str, str]) -> int:
    return client.post(
        "/api/search/papers",
        headers=headers,
        json={"query": "time series anomaly", "sources": ["fixture"], "limit": 1},
    ).json()["papers"][0]["id"]


def test_configured_provider_merges_valid_fields_and_persists_secret_free_audit(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = register(client)
        pid = paper_id(client, headers)
        app.state.analysis_provider = DeterministicMockProvider(
            {
                "research_background": "Industrial monitoring requires reliable alerts.",
                "citations": [{"field": "research_background", "chunk_id": None}],
            }
        )
        response = client.post(
            f"/api/papers/{pid}/analyze", headers=headers, json={"provider": "configured"}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["analysis_mode"] == "hybrid"
        assert body["provider"] == "deterministic_mock"
        assert body["analysis"]["research_background"] == "Industrial monitoring requires reliable alerts."

        with app.state.database.session() as session:
            row = session.get(PaperAnalysisRecord, body["id"])
            assert row is not None
            assert row.analysis_run_id
            assert row.provider == "deterministic_mock"
            run = session.scalar(select(AgentRun).where(AgentRun.run_id == row.analysis_run_id))
            tool = session.scalar(select(ToolCall).where(ToolCall.run_id == row.analysis_run_id))
            persisted = " ".join(
                [
                    run.input_json,
                    run.output_json,
                    run.error or "",
                    tool.input_json,
                    tool.output_json,
                    tool.error or "",
                ]
            )
            assert "never-persist-this-secret" not in persisted
            assert tool.validated_output_hash


def test_invalid_provider_output_falls_back_to_deterministic_analysis(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = register(client)
        pid = paper_id(client, headers)
        app.state.analysis_provider = DeterministicMockProvider(
            {"research_background": "No citation", "citations": []}
        )
        response = client.post(
            f"/api/papers/{pid}/analyze", headers=headers, json={"provider": "configured"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["analysis_mode"] == "deterministic_fallback"
        assert body["fallback_reason"].startswith("CitationValidationError")
        assert "never-persist-this-secret" not in json.dumps(body)


def test_default_analysis_remains_deterministic(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    object.__setattr__(settings, "analysis_provider", "deterministic")
    app = create_app(settings)
    with TestClient(app) as client:
        headers = register(client)
        pid = paper_id(client, headers)
        response = client.post(f"/api/papers/{pid}/analyze", headers=headers, json={})
        assert response.status_code == 200
        assert response.json()["analysis_mode"] == "deterministic"
