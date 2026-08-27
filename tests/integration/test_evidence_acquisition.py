import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select

from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.models import AgentRun, SourceRequest, ToolCall
from research_navigator.scholarly.base import (
    AdapterSearchResult,
    PaperRecord,
    ScholarlyAdapter,
    SearchRequest,
    SourceProvenance,
    SourceStatus,
)
from research_navigator.scholarly.service import FederatedSearchService


class MutableEvidenceAdapter(ScholarlyAdapter):
    name = "evidence_source"
    supports_evidence_acquisition = True

    def __init__(self, record: PaperRecord) -> None:
        self.record = record
        self.call_count = 0

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        self.call_count += 1
        return AdapterSearchResult(
            records=[self.record],
            status=SourceStatus(status="ok", result_count=1),
        )


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


def record(
    *,
    doi: str,
    abstract: str | None,
    arxiv_id: str | None = None,
    abstract_provenance: SourceProvenance | None = None,
) -> PaperRecord:
    provenance = SourceProvenance(
        source="evidence_source",
        source_id=doi,
        source_url="https://example.test/paper",
        raw_hash="a" * 64 if abstract is None else "b" * 64,
    )
    return PaperRecord(
        title="Evidence Acquisition for Industrial Alerts",
        abstract=abstract,
        publication_year=2026,
        doi=doi,
        arxiv_id=arxiv_id,
        source_urls=["https://example.test/paper"],
        source_provenance=[provenance],
        abstract_provenance=abstract_provenance or (provenance if abstract else None),
    )


def register(client: TestClient, email: str) -> dict[str, str]:
    payload = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "research-pass-123",
            "display_name": "Evidence Researcher",
        },
    ).json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


def test_metadata_only_paper_acquires_exact_abstract_reanalyzes_and_audits(
    tmp_path: Path,
) -> None:
    adapter = MutableEvidenceAdapter(record(doi="10.1000/evidence", abstract=None))
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        app.state.search_service = FederatedSearchService([adapter])
        headers = register(client, "acquire@example.com")
        paper_id = client.post(
            "/api/search/papers",
            headers=headers,
            json={
                "query": "10.1000/evidence",
                "sources": ["evidence_source"],
                "limit": 1,
                "mode": "precise",
            },
        ).json()["papers"][0]["id"]
        initial = client.post(f"/api/papers/{paper_id}/analyze", headers=headers, json={})
        assert initial.json()["analysis"]["evidence_level"] == "metadata_only"

        adapter.record = record(
            doi="10.1000/evidence",
            abstract=(
                "We study industrial multivariate time-series alert prediction and propose "
                "a bounded evidence acquisition workflow."
            ),
        )
        acquired = client.post(
            f"/api/papers/{paper_id}/acquire-evidence",
            headers=headers,
            json={"sources": ["evidence_source"]},
        )

        assert acquired.status_code == 200, acquired.text
        payload = acquired.json()
        assert payload["outcome"] == "abstract_acquired"
        assert payload["evidence_level_before"] == "metadata_only"
        assert payload["evidence_level_after"] == "abstract_only"
        assert payload["paper"]["abstract"].startswith("We study industrial")
        assert payload["paper"]["abstract_evidence_verified"] is True
        assert payload["analysis"]["analysis"]["evidence_level"] == "abstract_only"
        assert payload["queried_sources"] == ["evidence_source"]

        with app.state.database.session() as session:
            run = session.scalar(select(AgentRun).where(AgentRun.run_id == payload["run_id"]))
            assert run is not None
            assert run.workflow_type == "evidence_acquisition"
            assert run.status == "succeeded"
            assert json.loads(run.output_json)["outcome"] == "abstract_acquired"
            tool = session.scalar(select(ToolCall).where(ToolCall.run_id == run.run_id))
            assert tool is not None
            assert tool.tool_name == "scholarly_search.search_papers"
            assert tool.status == "succeeded"
            assert tool.user_id == run.user_id
            source_request = session.scalar(
                select(SourceRequest).where(SourceRequest.run_id == run.run_id)
            )
            assert source_request is not None
            assert source_request.user_id == run.user_id
            assert source_request.source == "evidence_source"
            assert source_request.project_id is None


def test_evidence_acquisition_rejects_identifier_conflict_without_mutating_paper(
    tmp_path: Path,
) -> None:
    adapter = MutableEvidenceAdapter(record(doi="10.1000/target", abstract=None))
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        app.state.search_service = FederatedSearchService([adapter])
        headers = register(client, "conflict@example.com")
        paper_id = client.post(
            "/api/search/papers",
            headers=headers,
            json={
                "query": "10.1000/target",
                "sources": ["evidence_source"],
                "limit": 1,
                "mode": "precise",
            },
        ).json()["papers"][0]["id"]
        adapter.record = record(
            doi="10.1000/different",
            abstract="This abstract belongs to a different paper and must not be merged.",
        )

        response = client.post(
            f"/api/papers/{paper_id}/acquire-evidence",
            headers=headers,
            json={"sources": ["evidence_source"]},
        )

        assert response.status_code == 200, response.text
        assert response.json()["outcome"] == "no_matching_evidence"
        assert response.json()["evidence_level_after"] == "metadata_only"
        paper = client.get(f"/api/papers/{paper_id}", headers=headers).json()
        assert paper["abstract"] is None


def test_evidence_acquisition_denies_foreign_project_before_calling_sources(
    tmp_path: Path,
) -> None:
    adapter = MutableEvidenceAdapter(record(doi="10.1000/private-project", abstract=None))
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        app.state.search_service = FederatedSearchService([adapter])
        owner_headers = register(client, "project-owner@example.com")
        project_id = client.post(
            "/api/projects",
            headers=owner_headers,
            json={"name": "Private evidence project"},
        ).json()["id"]
        paper_id = client.post(
            "/api/search/papers",
            headers=owner_headers,
            json={
                "query": "10.1000/private-project",
                "sources": ["evidence_source"],
                "limit": 1,
                "mode": "precise",
            },
        ).json()["papers"][0]["id"]
        attacker_headers = register(client, "project-attacker@example.com")
        adapter.record = record(
            doi="10.1000/private-project",
            abstract="This must not be fetched before project authorization succeeds.",
        )
        adapter.call_count = 0

        response = client.post(
            f"/api/papers/{paper_id}/acquire-evidence",
            headers=attacker_headers,
            json={"project_id": project_id, "sources": ["evidence_source"]},
        )

        assert response.status_code == 404
        assert adapter.call_count == 0
        paper = client.get(f"/api/papers/{paper_id}", headers=attacker_headers).json()
        assert paper["abstract"] is None
        with app.state.database.session() as session:
            assert session.scalar(select(AgentRun).where(AgentRun.project_id == project_id)) is None


def test_evidence_acquisition_falls_back_from_doi_to_arxiv(tmp_path: Path) -> None:
    initial = record(
        doi="10.1000/fallback",
        arxiv_id="2608.12345",
        abstract=None,
    )

    class FallbackAdapter(MutableEvidenceAdapter):
        async def search(self, request: SearchRequest) -> AdapterSearchResult:
            self.call_count += 1
            if request.query == "10.1000/fallback":
                return AdapterSearchResult(
                    records=[], status=SourceStatus(status="ok", result_count=0)
                )
            enriched = record(
                doi="10.1000/fallback",
                arxiv_id="2608.12345",
                abstract="The arXiv identifier supplied the exact abstract after DOI fallback.",
            )
            return AdapterSearchResult(
                records=[enriched], status=SourceStatus(status="ok", result_count=1)
            )

    adapter = FallbackAdapter(initial)
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        seed_adapter = MutableEvidenceAdapter(initial)
        app.state.search_service = FederatedSearchService([seed_adapter])
        headers = register(client, "fallback@example.com")
        paper_id = client.post(
            "/api/search/papers",
            headers=headers,
            json={
                "query": "10.1000/fallback",
                "sources": ["evidence_source"],
                "limit": 1,
                "mode": "precise",
            },
        ).json()["papers"][0]["id"]
        app.state.search_service = FederatedSearchService([adapter])
        adapter.call_count = 0

        response = client.post(
            f"/api/papers/{paper_id}/acquire-evidence",
            headers=headers,
            json={"sources": ["evidence_source"]},
        )

        assert response.status_code == 200, response.text
        assert response.json()["outcome"] == "abstract_acquired"
        assert adapter.call_count == 2


def test_adapter_without_explicit_acquisition_capability_is_never_called(tmp_path: Path) -> None:
    class UnapprovedAdapter(MutableEvidenceAdapter):
        name = "unapproved"
        supports_evidence_acquisition = False

    approved = MutableEvidenceAdapter(record(doi="10.1000/allowlist", abstract=None))
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        app.state.search_service = FederatedSearchService([approved])
        headers = register(client, "allowlist@example.com")
        paper_id = client.post(
            "/api/search/papers",
            headers=headers,
            json={
                "query": "10.1000/allowlist",
                "sources": ["evidence_source"],
                "limit": 1,
                "mode": "precise",
            },
        ).json()["papers"][0]["id"]
        unapproved = UnapprovedAdapter(
            record(
                doi="10.1000/allowlist",
                abstract="An unapproved adapter must never supply evidence.",
            )
        )
        app.state.search_service = FederatedSearchService([unapproved])

        response = client.post(
            f"/api/papers/{paper_id}/acquire-evidence",
            headers=headers,
            json={"sources": ["unapproved"]},
        )

        assert response.status_code == 200, response.text
        assert response.json()["outcome"] == "no_eligible_source"
        assert unapproved.call_count == 0


def test_fixture_abstract_cannot_be_promoted_by_mixed_provenance(tmp_path: Path) -> None:
    real_metadata = SourceProvenance(
        source="evidence_source",
        source_id="10.1000/mixed",
        source_url="https://example.test/real-metadata",
        raw_hash="c" * 64,
    )
    fixture_abstract = SourceProvenance(
        source="fixture",
        source_id="fixture-mixed",
        source_url="https://example.test/fixture",
        raw_hash="d" * 64,
        is_fixture=True,
    )
    adapter = MutableEvidenceAdapter(record(doi="10.1000/mixed", abstract=None))
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        app.state.search_service = FederatedSearchService([adapter])
        headers = register(client, "mixed@example.com")
        paper_id = client.post(
            "/api/search/papers",
            headers=headers,
            json={
                "query": "10.1000/mixed",
                "sources": ["evidence_source"],
                "limit": 1,
                "mode": "precise",
            },
        ).json()["papers"][0]["id"]
        adapter.record = PaperRecord(
            title="Evidence Acquisition for Industrial Alerts",
            abstract="Fixture text must not become real scholarly evidence.",
            publication_year=2026,
            doi="10.1000/mixed",
            source_provenance=[real_metadata, fixture_abstract],
            abstract_provenance=fixture_abstract,
        )

        response = client.post(
            f"/api/papers/{paper_id}/acquire-evidence",
            headers=headers,
            json={"sources": ["evidence_source"]},
        )

        assert response.status_code == 200, response.text
        assert response.json()["outcome"] == "no_matching_evidence"
        assert response.json()["paper"]["abstract"] is None


def test_failed_reanalysis_rolls_back_paper_and_finishes_failed_run(
    tmp_path: Path, monkeypatch
) -> None:
    adapter = MutableEvidenceAdapter(record(doi="10.1000/failure", abstract=None))
    app = create_app(settings_for(tmp_path))
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.search_service = FederatedSearchService([adapter])
        headers = register(client, "failure@example.com")
        paper_id = client.post(
            "/api/search/papers",
            headers=headers,
            json={
                "query": "10.1000/failure",
                "sources": ["evidence_source"],
                "limit": 1,
                "mode": "precise",
            },
        ).json()["papers"][0]["id"]
        adapter.record = record(
            doi="10.1000/failure",
            abstract="This update must roll back when reanalysis fails.",
        )

        def fail_analysis(*args, **kwargs):
            raise RuntimeError("forced reanalysis failure")

        monkeypatch.setattr(
            "research_navigator.analysis.acquisition.run_paper_analysis", fail_analysis
        )
        response = client.post(
            f"/api/papers/{paper_id}/acquire-evidence",
            headers=headers,
            json={"sources": ["evidence_source"]},
        )

        assert response.status_code == 502
        paper = client.get(f"/api/papers/{paper_id}", headers=headers).json()
        assert paper["abstract"] is None
        with app.state.database.session() as session:
            run = session.scalar(
                select(AgentRun)
                .where(AgentRun.workflow_type == "evidence_acquisition")
                .order_by(AgentRun.id.desc())
            )
            assert run is not None
            assert run.status == "failed"
            assert run.finished_at is not None
            assert run.error == "RuntimeError: forced reanalysis failure"


def test_evidence_acquisition_limits_requested_source_count(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = register(client, "source-limit@example.com")
        response = client.post(
            "/api/papers/1/acquire-evidence",
            headers=headers,
            json={"sources": [f"source-{index}" for index in range(9)]},
        )
        assert response.status_code == 422


def test_unverified_fixture_abstract_is_not_used_by_normal_analysis(tmp_path: Path) -> None:
    fixture_provenance = SourceProvenance(
        source="fixture",
        source_id="fixture-existing",
        source_url="https://example.test/fixture",
        raw_hash="e" * 64,
        is_fixture=True,
    )
    adapter = MutableEvidenceAdapter(
        PaperRecord(
            title="Evidence Acquisition for Industrial Alerts",
            abstract="Fixture prose must never be analyzed as scholarly evidence.",
            publication_year=2026,
            doi="10.1000/fixture-existing",
            source_provenance=[fixture_provenance],
            abstract_provenance=fixture_provenance,
        )
    )
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        app.state.search_service = FederatedSearchService([adapter])
        headers = register(client, "fixture-boundary@example.com")
        paper_id = client.post(
            "/api/search/papers",
            headers=headers,
            json={
                "query": "10.1000/fixture-existing",
                "sources": ["evidence_source"],
                "limit": 1,
                "mode": "precise",
            },
        ).json()["papers"][0]["id"]

        response = client.post(f"/api/papers/{paper_id}/analyze", headers=headers, json={})

        assert response.status_code == 200, response.text
        assert response.json()["analysis"]["evidence_level"] == "metadata_only"


def test_existing_fulltext_skips_external_acquisition_and_preserves_level(
    tmp_path: Path,
) -> None:
    adapter = MutableEvidenceAdapter(record(doi="10.1000/fulltext", abstract=None))
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        app.state.search_service = FederatedSearchService([adapter])
        headers = register(client, "fulltext-boundary@example.com")
        paper_id = client.post(
            "/api/search/papers",
            headers=headers,
            json={
                "query": "10.1000/fulltext",
                "sources": ["evidence_source"],
                "limit": 1,
                "mode": "precise",
            },
        ).json()["papers"][0]["id"]
        buffer = BytesIO()
        canvas = Canvas(buffer)
        canvas.drawString(72, 760, "Authorized fulltext evidence.")
        canvas.save()
        uploaded = client.post(
            f"/api/papers/{paper_id}/upload",
            headers=headers,
            data={"rights_confirmed": "true"},
            files={"file": ("authorized.pdf", buffer.getvalue(), "application/pdf")},
        )
        assert uploaded.status_code == 201, uploaded.text
        adapter.call_count = 0

        response = client.post(
            f"/api/papers/{paper_id}/acquire-evidence",
            headers=headers,
            json={"sources": ["evidence_source"]},
        )

        assert response.status_code == 200, response.text
        assert response.json()["outcome"] == "already_sufficient"
        assert response.json()["evidence_level_before"] == "user_uploaded_fulltext"
        assert response.json()["evidence_level_after"] == "user_uploaded_fulltext"
        assert adapter.call_count == 0
