from pathlib import Path

from fastapi.testclient import TestClient

from research_navigator.config import Settings
from research_navigator.main import create_app


def make_client(tmp_path: Path) -> TestClient:
    data_dir = tmp_path / "state"
    settings = Settings(
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
    return TestClient(create_app(settings))


def register(client: TestClient, email: str) -> dict[str, object]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "research-pass-123", "display_name": email.split("@")[0]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_header(payload: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {payload['access_token']}"}


def test_register_login_profile_and_project_are_persistent(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        registration = register(client, "student@example.com")
        headers = auth_header(registration)

        me = client.get("/api/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["email"] == "student@example.com"

        profile = client.put(
            "/api/research-profiles/me",
            headers=headers,
            json={
                "stage": "硕士一年级",
                "major": "大数据技术与工程",
                "broad_direction": "多变量时序异常检测",
                "keywords": ["future horizon", "alert ranking"],
                "excluded_terms": ["图像异常检测"],
                "preferences": ["复现优先", "工程应用"],
                "compute_constraints": "单卡 24GB GPU",
            },
        )
        assert profile.status_code == 200
        assert profile.json()["broad_direction"] == "多变量时序异常检测"

        created = client.post(
            "/api/projects",
            headers=headers,
            json={
                "name": "未来窗口异常风险排序",
                "description": "历史窗口预测未来 Horizon 内的异常风险",
                "broad_direction": "时序异常预测",
            },
        )
        assert created.status_code == 201
        project_id = created.json()["id"]

        listed = client.get("/api/projects", headers=headers)
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [project_id]

        login = client.post(
            "/api/auth/login",
            json={"email": "student@example.com", "password": "research-pass-123"},
        )
        assert login.status_code == 200
        assert login.json()["access_token"] != registration["access_token"]


def test_projects_are_isolated_between_users(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        first = register(client, "first@example.com")
        second = register(client, "second@example.com")

        created = client.post(
            "/api/projects",
            headers=auth_header(first),
            json={"name": "Private research", "description": None, "broad_direction": "TSAD"},
        )
        project_id = created.json()["id"]

        denied = client.get(f"/api/projects/{project_id}", headers=auth_header(second))
        assert denied.status_code == 404

        visible = client.get(f"/api/projects/{project_id}", headers=auth_header(first))
        assert visible.status_code == 200


def test_logout_revokes_session(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        registration = register(client, "logout@example.com")
        headers = auth_header(registration)

        assert client.post("/api/auth/logout", headers=headers).status_code == 204
        assert client.get("/api/auth/me", headers=headers).status_code == 401
