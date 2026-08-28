from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.scholarly.base import SourceStatus
from research_navigator.scholarly.runtime import SourceRuntimeRepository


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
        enable_openalex=True,
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


def authenticate(client: TestClient) -> dict[str, str]:
    payload = client.post(
        "/api/auth/register",
        json={
            "email": "runtime@example.com",
            "password": "research-pass-123",
            "display_name": "Runtime User",
        },
    ).json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


def test_rate_limit_state_blocks_repeated_calls_and_is_visible_in_source_status(
    tmp_path: Path,
) -> None:
    app = create_app(settings_for(tmp_path))
    now = datetime.now(UTC)
    with TestClient(app) as client:
        headers = authenticate(client)
        with app.state.database.session() as session:
            repository = SourceRuntimeRepository(session)
            repository.after_call(
                "openalex",
                SourceStatus(
                    status="rate_limited",
                    detail="OpenAlex returned 429",
                    metadata={
                        "http_status": 429,
                        "retry_after_seconds": 60,
                        "rate_limit_remaining": 0,
                    },
                ),
                now=now,
            )
            session.commit()

        with app.state.database.session() as session:
            blocked = SourceRuntimeRepository(session).before_call(
                "openalex", now=now + timedelta(seconds=10)
            )
            assert blocked is not None
            assert blocked.status == "rate_limited"
            assert blocked.metadata["cooldown_until"] == (now + timedelta(seconds=60)).isoformat()

        response = client.get("/api/sources/status", headers=headers)
        assert response.status_code == 200
        openalex = next(item for item in response.json() if item["name"] == "openalex")
        assert openalex["status"] == "rate_limited"
        assert openalex["cooldown_until"] is not None
        assert openalex["metadata"]["rate_limit_remaining"] == 0


def test_success_after_cooldown_clears_failure_state(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    now = datetime.now(UTC)
    with TestClient(app), app.state.database.session() as session:
        repository = SourceRuntimeRepository(session)
        repository.after_call(
            "openalex",
            SourceStatus(
                status="rate_limited",
                metadata={"http_status": 429, "retry_after_seconds": 1},
            ),
            now=now,
        )
        repository.after_call(
            "openalex",
            SourceStatus(
                status="ok",
                metadata={"http_status": 200, "rate_limit_remaining": 999},
            ),
            now=now + timedelta(seconds=2),
        )
        session.commit()
        assert repository.before_call("openalex", now=now + timedelta(seconds=3)) is None
        row = repository.get("openalex")
        assert row is not None
        assert row.operational_status == "ok"
        assert row.consecutive_failures == 0
        assert row.cooldown_until is None
