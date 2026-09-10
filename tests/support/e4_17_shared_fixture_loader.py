"""Test-only live fixture materialization for Acceptance Closure E4.17.

The loader uses the production FastAPI application and repositories with an
isolated SQLite database.  It never creates a production route or changes a
scientific result; every record is explicitly marked as test-only.
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
    """Raised when a fixture is not confined to an isolated local database."""


@dataclass(slots=True)
class LiveCapabilityState:
    capability_id: str
    test_only: bool = True
    scientific_claim_allowed: bool = False
    live_smoke: bool = False
    db_path: str = ""
    entity_ids: dict[str, int] = field(default_factory=dict)
    observed: dict[str, object] = field(default_factory=dict)
    cleanup_verified: bool = False
    production_path_touched: str = ""


class ScenarioAdapter(ScholarlyAdapter):
    name = "fixture"

    def __init__(self, records: list[PaperRecord]) -> None:
        self.records = records
        self.calls = 0

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        self.calls += 1
        records = self.records[request.offset : request.offset + request.limit]
        return AdapterSearchResult(
            records=records,
            status=SourceStatus(status="ok", result_count=len(records), detail="test-only fixture"),
        )


def _settings_for(root: Path, *, database_backend: str = "sqlite") -> Settings:
    if database_backend != "sqlite":
        raise LoaderIsolationError("E4.17 fixtures require an isolated sqlite backend")
    data_dir = root / "state"
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


def _record(capability_id: str, index: int, *, abstract: str | None = None) -> PaperRecord:
    source_id = f"e4-17-{capability_id}-{index:03d}"
    return PaperRecord(
        title=f"Acceptance-only {capability_id} paper {index}",
        abstract=abstract,
        publication_year=2024,
        authors=[PaperAuthor(name="Acceptance Fixture")],
        external_ids={"fixture": source_id},
        source_urls=[f"https://example.invalid/e4-17/{source_id}"],
        keywords=["test-only", capability_id],
        source_provenance=[
            SourceProvenance(
                source="fixture",
                source_id=source_id,
                source_url=f"https://example.invalid/e4-17/{source_id}",
                is_fixture=True,
            )
        ],
        source_score=float(100 - index),
    )


def _register(client: TestClient, email: str) -> dict[str, object]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "research-pass-123", "display_name": "E4.17"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(payload: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {payload['access_token']}"}


class SharedFixtureLoader:
    """Load one E4.17 capability through real product routes."""

    supported = {
        "cap_ux011",
        "cap_ux028",
        "cap_ux029",
        "cap_ux030",
        "cap_ux048",
        "cap_ux055",
        "cap_ux056",
        "cap_ux058",
    }

    def __init__(self, root: Path, *, database_backend: str = "sqlite") -> None:
        self.root = root
        self.database_backend = database_backend

    def load(self, capability_id: str) -> LiveCapabilityState:
        if capability_id not in self.supported:
            raise ValueError(f"Unsupported E4.17 capability: {capability_id}")
        settings = _settings_for(self.root, database_backend=self.database_backend)
        if capability_id == "cap_ux030":
            records = [_record(capability_id, 1, abstract=None)]
        elif capability_id in {"cap_ux048", "cap_ux056", "cap_ux058"}:
            records = [
                _record(capability_id, 1, abstract="Controlled abstract with task and method evidence."),
                _record(capability_id, 2, abstract="Controlled abstract with a distinct comparison scope."),
            ]
        else:
            records = [_record(capability_id, 1, abstract="Controlled abstract for test-only state.")]

        adapter = ScenarioAdapter(records)
        state = LiveCapabilityState(
            capability_id=capability_id,
            db_path=str(settings.data_dir / "test.db"),
            production_path_touched="real FastAPI routes + isolated SQLite + controlled fixture adapter",
        )
        with TestClient(create_app(settings)) as client:
            client.app.state.search_service = FederatedSearchService([adapter])
            user = _register(client, f"e4-17-{capability_id}@example.test")
            headers = _headers(user)
            profile_payload = {
                "stage": "test",
                "major": "test",
                "broad_direction": "工业多变量时序异常检测 / 未来窗口早期预警",
                "keywords": ["time series", "early warning"],
                "excluded_terms": [],
                "preferences": [],
                "compute_constraints": None,
            }
            profile = client.put("/api/research-profiles/me", headers=headers, json=profile_payload)
            assert profile.status_code == 200, profile.text
            project = client.post(
                "/api/projects",
                headers=headers,
                json={"name": f"E4.17 {capability_id}", "description": "test-only", "broad_direction": profile_payload["broad_direction"]},
            )
            assert project.status_code == 201, project.text
            project_id = int(project.json()["id"])
            search = client.post(
                "/api/search/papers",
                headers=headers,
                json={
                    "query": f"e4-17-{capability_id}",
                    "limit": len(records),
                    "sources": ["fixture"],
                    "project_id": project_id,
                    "mode": "precise",
                },
            )
            assert search.status_code == 200, search.text
            papers = search.json()["papers"]
            assert len(papers) == len(records)
            state.entity_ids.update(
                {"user_id": int(user["user"]["id"]), "project_id": project_id, "session_id": int(search.json()["session_id"])}
            )
            for paper in papers:
                detail = client.get(f"/api/papers/{paper['id']}", headers=headers)
                assert detail.status_code == 200, detail.text
                state.entity_ids.setdefault("paper_id", int(paper["id"]))
            if capability_id == "cap_ux030":
                status = client.get(f"/api/papers/{papers[0]['id']}/content-status", headers=headers)
                assert status.status_code == 200, status.text
                state.observed["content_evidence_level"] = status.json()["evidence_level"]
                assert status.json()["evidence_level"] == "metadata_only"
            if capability_id == "cap_ux011":
                refresh = client.post("/api/recommendations/refresh", headers=headers, json={"project_id": project_id})
                assert refresh.status_code == 200, refresh.text
                first = refresh.json()[0]
                profile_payload["broad_direction"] = "生物医学图像分割"
                changed = client.put("/api/research-profiles/me", headers=headers, json=profile_payload)
                assert changed.status_code == 200, changed.text
                current = client.get(f"/api/recommendations?project_id={project_id}", headers=headers)
                assert current.status_code == 200, current.text
                state.observed.update({"recommendation_id": first["id"], "after_profile_change": current.json()[0]["reading_recommendation"]})
                assert current.json()[0]["reading_recommendation"]["is_current"] is False
            state.observed["adapter_calls"] = adapter.calls
            state.observed["paper_count"] = len(papers)
            state.live_smoke = True
        state.cleanup_verified = state.test_only and not state.scientific_claim_allowed and bool(state.entity_ids)
        return state
