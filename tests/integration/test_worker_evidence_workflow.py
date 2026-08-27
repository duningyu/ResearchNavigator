from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.open_access.base import OpenAccessResolution
from research_navigator.scholarly.base import (
    AdapterSearchResult,
    PaperRecord,
    ScholarlyAdapter,
    SearchRequest,
    SourceProvenance,
    SourceStatus,
)
from research_navigator.scholarly.service import FederatedSearchService
from services.worker.main import run_once


class Adapter(ScholarlyAdapter):
    name = "worker_source"
    supports_evidence_acquisition = True

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        provenance = SourceProvenance(
            source=self.name,
            source_id="10.1000/worker-evidence",
            source_url="https://example.test/worker-evidence",
            raw_hash="d" * 64,
        )
        return AdapterSearchResult(
            records=[
                PaperRecord(
                    title="Worker Evidence Workflow",
                    abstract="The worker executes an audited evidence workflow.",
                    publication_year=2026,
                    doi="10.1000/worker-evidence",
                    source_provenance=[provenance],
                    abstract_provenance=provenance,
                )
            ],
            status=SourceStatus(status="ok", result_count=1),
        )


class NoOA:
    async def resolve(self, identity: object) -> OpenAccessResolution:
        return OpenAccessResolution()


def settings_for(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "state"
    return Settings(
        data_dir=data_dir,
        database_url=f"sqlite+pysqlite:///{(data_dir / 'test.db').as_posix()}",
        upload_dir=data_dir / "uploads",
        vector_dir=data_dir / "vectors",
        backup_dir=data_dir / "backups",
        allowed_origins=("http://localhost:5173",),
        enable_fixture_source=False,
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


def register(client: TestClient) -> dict[str, str]:
    payload = client.post(
        "/api/auth/register",
        json={
            "email": "worker-workflow@example.com",
            "password": "research-pass-123",
            "display_name": "Worker",
        },
    ).json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


def test_worker_executes_evidence_workflow_to_partial_terminal_state(
    tmp_path: Path, monkeypatch
) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    adapter = Adapter()
    with TestClient(app) as client:
        headers = register(client)
        app.state.search_service = FederatedSearchService([adapter])
        paper_id = client.post(
            "/api/search/papers",
            headers=headers,
            json={
                "query": "10.1000/worker-evidence",
                "sources": ["worker_source"],
                "limit": 1,
                "mode": "precise",
            },
        ).json()["papers"][0]["id"]
        job = client.post(
            f"/api/papers/{paper_id}/evidence-workflows",
            headers=headers,
            json={"sources": ["worker_source"]},
        ).json()

        monkeypatch.setattr(
            "services.worker.main.build_search_service",
            lambda _: FederatedSearchService([adapter]),
        )
        monkeypatch.setattr(
            "services.worker.main.build_open_access_resolver", lambda _: NoOA()
        )
        assert run_once(app.state.database, settings=settings) == job["id"]
        completed = client.get(
            f"/api/evidence-workflows/{job['id']}", headers=headers
        ).json()
        assert completed["status"] == "partial"
        assert completed["terminal"] is True
        assert completed["strongest_evidence"] == "abstract_only"
        assert completed["attempt_count"] == 1
        assert completed["events"][-1]["event_type"] == "partial"
