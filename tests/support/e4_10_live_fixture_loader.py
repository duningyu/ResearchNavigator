"""Live, test-only state loader for Acceptance Closure E4.10.

This module deliberately starts the real FastAPI application against an isolated
SQLite database.  Controlled scholarly data is injected at the adapter boundary;
product routes, auth, persistence, and ownership checks remain real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.scholarly.base import (
    AdapterSearchResult,
    PaperAuthor,
    PaperRecord,
    ScholarlyAdapter,
    SearchRequest,
    SourceProvenance,
    SourceStatus,
)
from research_navigator.scholarly.service import FederatedSearchService


class LoaderIsolationError(RuntimeError):
    """Raised when a loader is asked to use a non-isolated runtime."""


@dataclass(slots=True)
class LiveFixtureState:
    capability_id: str
    state_owner: str
    test_only: bool
    scientific_claim_allowed: bool
    live_smoke: bool = False
    observed_result_count: int = 0
    session_id: int | None = None
    entity_ids: dict[str, int] = field(default_factory=dict)
    db_path: str = ""
    production_path_touched: str = ""
    cleanup_strategy: str = ""
    cleanup_verified: bool = False


class ControlledFixtureAdapter(ScholarlyAdapter):
    name = "fixture"

    def __init__(self, records: list[PaperRecord]) -> None:
        self.records = records
        self.calls = 0

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        self.calls += 1
        records = self.records[request.offset : request.offset + request.limit]
        return AdapterSearchResult(
            records=records,
            status=SourceStatus(status="ok", result_count=len(records), detail="test-only adapter"),
        )


def _settings_for(root: Path, *, database_backend: str = "sqlite") -> Settings:
    data_dir = root / "state"
    if database_backend != "sqlite":
        raise LoaderIsolationError("E4.10 loader requires an isolated sqlite backend")
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
        database_backend="sqlite",
        storage_backend="local",
    )


def _record(index: int) -> PaperRecord:
    return PaperRecord(
        title=f"Test-only result {index:03d}",
        abstract="Synthetic UI behavior material; not research evidence.",
        publication_year=2024,
        authors=[PaperAuthor(name="Acceptance Fixture")],
        external_ids={"fixture": f"e4-10-{index:03d}"},
        source_urls=[f"https://example.invalid/e4-10/{index:03d}"],
        keywords=["test-only", "acceptance"],
        source_provenance=[
            SourceProvenance(
                source="fixture",
                source_id=f"e4-10-{index:03d}",
                source_url=f"https://example.invalid/e4-10/{index:03d}",
                is_fixture=True,
            )
        ],
        source_score=float(100 - index),
    )


def _register(client: TestClient, email: str) -> dict[str, object]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "research-pass-123", "display_name": email.split("@")[0]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(payload: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {payload['access_token']}"}


class LiveFixtureLoader:
    """Materialize small, isolated states through real product routes."""

    def __init__(self, root: Path, *, database_backend: str = "sqlite") -> None:
        self.root = root
        self.database_backend = database_backend

    def load(self, capability_id: str) -> LiveFixtureState:
        if capability_id not in {"cap_ux001", "cap_ux002", "cap_ux025", "cap_ux078"}:
            raise ValueError(f"Unsupported E4.10 vertical slice: {capability_id}")
        settings = _settings_for(self.root, database_backend=self.database_backend)
        records = [] if capability_id == "cap_ux025" else [_record(index) for index in range(60)]
        adapter = ControlledFixtureAdapter(records)
        state_owner = (
            "EXTERNAL_ADAPTER"
            if capability_id == "cap_ux025"
            else "BROWSER_SESSION"
            if capability_id == "cap_ux002"
            else "DATABASE_SERVICE"
            if capability_id == "cap_ux001"
            else "AUTHORIZATION"
        )
        state = LiveFixtureState(
            capability_id=capability_id,
            state_owner=state_owner,
            test_only=True,
            scientific_claim_allowed=False,
            db_path=str(settings.data_dir / "test.db"),
            production_path_touched="real FastAPI routes + isolated SQLite; controlled adapter boundary",
            cleanup_strategy="pytest temporary-root disposal; no shared database rows",
        )
        with TestClient(create_app(settings)) as client:
            client.app.state.search_service = FederatedSearchService([adapter])
            first = _register(client, f"e4-10-{capability_id}-a@example.test")
            first_headers = _headers(first)
            project = client.post(
                "/api/projects",
                headers=first_headers,
                json={"name": f"E4.10 {capability_id}", "description": "test-only", "broad_direction": "test"},
            )
            assert project.status_code == 201, project.text
            project_id = int(project.json()["id"])
            payload = client.post(
                "/api/search/papers",
                headers=first_headers,
                json={
                    "query": "e4-10-empty" if capability_id == "cap_ux025" else "e4-10-long-list",
                    "limit": 60,
                    "sources": ["fixture"],
                    "project_id": project_id,
                    "mode": "precise",
                },
            )
            assert payload.status_code == 200, payload.text
            search = payload.json()
            state.observed_result_count = int(search["result_count"])
            state.session_id = int(search["session_id"])
            state.entity_ids.update({"project_id": project_id, "paper_count": state.observed_result_count})
            session = client.get(f"/api/search/sessions/{state.session_id}", headers=first_headers)
            assert session.status_code == 200, session.text
            assert session.json()["project_id"] == project_id

            if capability_id == "cap_ux078":
                second = _register(client, "e4-10-cap-ux078-b@example.test")
                denied = client.get(f"/api/projects/{project_id}", headers=_headers(second))
                state.entity_ids.update({"account_count": 2, "forbidden_status": denied.status_code})
                assert denied.status_code == 404, denied.text
            if capability_id == "cap_ux025":
                assert state.observed_result_count == 0
                assert search["source_status"]["fixture"]["status"] == "ok"
            else:
                assert state.observed_result_count == 60
                papers = client.get(
                    f"/api/search/sessions/{state.session_id}/papers", headers=first_headers
                )
                assert papers.status_code == 200, papers.text
                assert len(papers.json()) == 60
            state.live_smoke = True
        state.cleanup_verified = self._verify_cleanup_scope(state)
        return state

    @staticmethod
    def _verify_cleanup_scope(state: LiveFixtureState) -> bool:
        return state.test_only and not state.scientific_claim_allowed and bool(state.entity_ids)
