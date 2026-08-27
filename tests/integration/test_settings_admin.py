from pathlib import Path

from fastapi.testclient import TestClient

from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.models import User


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
        enable_semantic_scholar=True,
        semantic_scholar_api_key="secret-scholar-key",
        unpaywall_email=None,
        crossref_mailto=None,
        llm_base_url="https://llm.invalid/v1",
        llm_api_key="secret-llm-key",
        llm_model="test-model",
        max_pdf_bytes=2_000_000,
        session_ttl_hours=24,
        environment="test",
    )


def register(client: TestClient, email: str) -> tuple[dict[str, str], dict]:
    auth = client.post(
        "/api/auth/register",
        json={"email": email, "password": "research-pass-123", "display_name": email},
    ).json()
    return {"Authorization": f"Bearer {auth['access_token']}"}, auth


def test_user_settings_are_persisted_and_user_scoped(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        first, _ = register(client, "settings-a@example.com")
        second, _ = register(client, "settings-b@example.com")
        initial = client.get("/api/settings/me", headers=first)
        assert initial.status_code == 200
        assert initial.json()["default_result_count"] == 50
        updated = client.put(
            "/api/settings/me",
            headers=first,
            json={
                "default_result_count": 20,
                "default_page_size": 10,
                "preferred_sources": ["fixture", "openalex"],
                "default_open_access_only": True,
                "display_language": "zh-CN",
                "analysis_execution_preference": "queued",
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["preferred_sources"] == ["fixture", "openalex"]
        assert client.get("/api/settings/me", headers=first).json()["default_result_count"] == 20
        assert client.get("/api/settings/me", headers=second).json()["default_result_count"] == 50


def test_admin_runtime_config_is_whitelisted_persisted_and_never_returns_secrets(
    tmp_path: Path,
) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers, auth = register(client, "runtime-admin@example.com")
        assert client.get("/api/admin/runtime-config", headers=headers).status_code == 403
        with app.state.database.session() as session:
            user = session.get(User, auth["user"]["id"])
            assert user is not None
            user.is_admin = True
            session.commit()

        before = client.get("/api/admin/runtime-config", headers=headers)
        assert before.status_code == 200
        assert before.json()["worker_max_attempts_default"] == 3
        updated = client.put(
            "/api/admin/runtime-config",
            headers=headers,
            json={"source_health_timeout_seconds": 3.5, "worker_max_attempts_default": 2},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["source_health_timeout_seconds"] == 3.5
        assert updated.json()["worker_max_attempts_default"] == 2
        assert "secret-scholar-key" not in updated.text
        assert "secret-llm-key" not in updated.text
        assert (app.state.settings.data_dir / "admin_runtime_config.json").exists()


def test_admin_config_status_reports_openalex_and_analysis_provider_without_secrets(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    settings = replace(
        settings_for(tmp_path),
        openalex_api_key="secret-openalex-key",
        analysis_provider="openai_compatible",
        analysis_prompt_version="paper-analysis-v2",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        headers, auth = register(client, "provider-admin@example.com")
        with app.state.database.session() as session:
            user = session.get(User, auth["user"]["id"])
            assert user is not None
            user.is_admin = True
            session.commit()

        response = client.get("/api/admin/config-status", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json() == {
            "semantic_scholar_key_configured": True,
            "openalex_api_key_configured": True,
            "llm_key_configured": True,
            "analysis_provider": "openai_compatible",
            "analysis_prompt_version": "paper-analysis-v2",
        }
        assert "secret-openalex-key" not in response.text
        assert "secret-llm-key" not in response.text
