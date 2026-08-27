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


def register_admin(client: TestClient, app) -> dict[str, str]:
    payload = client.post(
        "/api/auth/register",
        json={
            "email": "backup-admin@example.com",
            "password": "research-pass-123",
            "display_name": "Admin",
        },
    ).json()
    with app.state.database.session() as session:
        user = session.get(User, payload["user"]["id"])
        assert user is not None
        user.is_admin = True
        session.commit()
    return {"Authorization": f"Bearer {payload['access_token']}"}


def login(client: TestClient) -> dict[str, str]:
    payload = client.post(
        "/api/auth/login",
        json={"email": "backup-admin@example.com", "password": "research-pass-123"},
    ).json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


def test_admin_can_create_stage_and_apply_backup_on_next_start(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    backup_name: str
    with TestClient(app) as client:
        headers = register_admin(client, app)
        project = client.post(
            "/api/projects",
            headers=headers,
            json={
                "name": "Original direction",
                "description": "before backup",
                "broad_direction": "TSAD",
            },
        ).json()
        created = client.post("/api/admin/backups", headers=headers)
        assert created.status_code == 201, created.text
        backup = created.json()
        backup_name = backup["name"]
        assert backup["sha256"]
        assert backup["size_bytes"] > 0
        listing = client.get("/api/admin/backups", headers=headers)
        assert any(item["name"] == backup_name for item in listing.json())

        changed = client.put(
            f"/api/projects/{project['id']}",
            headers=headers,
            json={"name": "Mutated after backup"},
        )
        assert changed.json()["name"] == "Mutated after backup"
        staged = client.post(
            f"/api/admin/backups/{backup_name}/stage-restore",
            headers=headers,
            json={"confirm_restore": True},
        )
        assert staged.status_code == 202, staged.text
        assert staged.json()["restart_required"] is True
        assert (settings.data_dir / "pending_restore.json").exists()

    # A process restart is the safety boundary. Startup applies the staged restore
    # before opening SQLite.
    restored_app = create_app(settings)
    with TestClient(restored_app) as client:
        headers = login(client)
        projects = client.get("/api/projects", headers=headers).json()
        assert projects[0]["name"] == "Original direction"
        assert not (settings.data_dir / "pending_restore.json").exists()


def test_non_admin_cannot_access_backups(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        auth = client.post(
            "/api/auth/register",
            json={
                "email": "user@example.com",
                "password": "research-pass-123",
                "display_name": "User",
            },
        ).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        assert client.get("/api/admin/backups", headers=headers).status_code == 403
        assert client.post("/api/admin/backups", headers=headers).status_code == 403
