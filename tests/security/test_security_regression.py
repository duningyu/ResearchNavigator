from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.models import User


def test_admin_config_status_enforces_permission_and_never_returns_secrets(tmp_path: Path) -> None:
    data_dir = tmp_path / "state"
    app = create_app(
        Settings(
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
            semantic_scholar_api_key="never-return-this-key",
            unpaywall_email=None,
            crossref_mailto=None,
            llm_base_url="https://llm.example/v1",
            llm_api_key="never-return-this-llm-key",
            llm_model="audit-model",
            max_pdf_bytes=100,
            session_ttl_hours=24,
            environment="test",
        )
    )
    with TestClient(app) as client:
        registration = client.post(
            "/api/auth/register",
            json={
                "email": "admin-audit@example.com",
                "password": "research-pass-123",
                "display_name": "Admin Audit",
            },
        ).json()
        headers = {"Authorization": f"Bearer {registration['access_token']}"}
        assert client.get("/api/admin/config-status", headers=headers).status_code == 403
        with app.state.database.session() as session:
            user = session.get(User, registration["user"]["id"])
            assert user is not None
            user.is_admin = True
            session.commit()
        response = client.get("/api/admin/config-status", headers=headers)
        assert response.status_code == 200
        assert response.json() == {
            "semantic_scholar_key_configured": True,
            "openalex_api_key_configured": False,
            "llm_key_configured": True,
            "analysis_provider": "deterministic",
            "analysis_prompt_version": "paper-analysis-v2",
        }
        assert "never-return" not in response.text


def test_protected_routes_reject_unauthenticated_request(tmp_path: Path) -> None:
    data_dir = tmp_path / "unauth"
    settings = Settings.from_env()
    settings = Settings(
        **{
            **{name: getattr(settings, name) for name in settings.__dataclass_fields__},
            "data_dir": data_dir,
            "database_url": f"sqlite+pysqlite:///{(data_dir / 'test.db').as_posix()}",
            "upload_dir": data_dir / "uploads",
            "vector_dir": data_dir / "vectors",
            "backup_dir": data_dir / "backups",
        }
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/projects").status_code == 401
