from pathlib import Path

from fastapi.testclient import TestClient

from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.models import User


def settings_from_env(tmp_path: Path, monkeypatch, *, public_demo: bool) -> Settings:
    data_dir = tmp_path / ("demo" if public_demo else "local")
    monkeypatch.setenv("RN_DATA_DIR", str(data_dir))
    monkeypatch.setenv(
        "RN_DATABASE_URL", f"sqlite+pysqlite:///{(data_dir / 'test.db').as_posix()}"
    )
    monkeypatch.setenv("RN_PUBLIC_DEMO_MODE", "1" if public_demo else "0")
    monkeypatch.setenv("RN_ENABLE_OPENALEX", "0")
    monkeypatch.setenv("RN_ENABLE_CROSSREF", "0")
    monkeypatch.setenv("RN_ENABLE_ARXIV", "0")
    monkeypatch.setenv("RN_ENABLE_SEMANTIC_SCHOLAR", "0")
    return Settings.from_env()


def register_admin(client: TestClient, app) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "public-demo-admin@example.test",
            "password": "research-pass-123",
            "display_name": "Demo Admin",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    with app.state.database.session() as session:
        user = session.get(User, payload["user"]["id"])
        assert user is not None
        user.is_admin = True
        session.commit()
    return {"Authorization": f"Bearer {payload['access_token']}"}


def assert_demo_restricted(response) -> None:
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "DEMO_MODE_RESTRICTED"


def test_public_demo_blocks_restricted_admin_operations(tmp_path: Path, monkeypatch) -> None:
    app = create_app(settings_from_env(tmp_path, monkeypatch, public_demo=True))
    with TestClient(app) as client:
        headers = register_admin(client, app)

        assert_demo_restricted(
            client.put(
                "/api/admin/runtime-config",
                headers=headers,
                json={"source_health_timeout_seconds": 3.0, "worker_max_attempts_default": 2},
            )
        )
        assert_demo_restricted(client.post("/api/admin/backups", headers=headers))
        assert_demo_restricted(
            client.get("/api/admin/backups/backup.zip/download", headers=headers)
        )
        assert_demo_restricted(
            client.post(
                "/api/admin/backups/backup.zip/stage-restore",
                headers=headers,
                json={"confirm_restore": True},
            )
        )
        assert_demo_restricted(
            client.post(
                "/api/admin/backfills/abstract-provenance",
                headers=headers,
                json={"dry_run": True, "batch_size": 1, "sources": ["fixture"]},
            )
        )


def test_normal_local_mode_keeps_admin_operations_available(tmp_path: Path, monkeypatch) -> None:
    app = create_app(settings_from_env(tmp_path, monkeypatch, public_demo=False))
    with TestClient(app) as client:
        headers = register_admin(client, app)
        updated = client.put(
            "/api/admin/runtime-config",
            headers=headers,
            json={"source_health_timeout_seconds": 3.0, "worker_max_attempts_default": 2},
        )
        assert updated.status_code == 200, updated.text
        backup = client.post("/api/admin/backups", headers=headers)
        assert backup.status_code == 201, backup.text
