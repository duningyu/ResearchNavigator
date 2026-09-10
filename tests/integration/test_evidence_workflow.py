from __future__ import annotations

from io import BytesIO
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from reportlab.pdfgen.canvas import Canvas

from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.models import Job
from research_navigator.open_access.base import (
    OpenAccessCandidate,
    OpenAccessResolution,
)
from research_navigator.open_access.fetcher import PdfFetchResult
from research_navigator.scholarly.base import (
    AdapterSearchResult,
    PaperRecord,
    ScholarlyAdapter,
    SearchRequest,
    SourceProvenance,
    SourceStatus,
)
from research_navigator.scholarly.service import FederatedSearchService


class EvidenceAdapter(ScholarlyAdapter):
    name = "evidence_source"
    supports_evidence_acquisition = True

    def __init__(self, record: PaperRecord) -> None:
        self.record = record

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        return AdapterSearchResult(
            records=[self.record], status=SourceStatus(status="ok", result_count=1)
        )


class StaticResolver:
    def __init__(self, resolution: OpenAccessResolution) -> None:
        self.resolution = resolution

    async def resolve(self, identity: object) -> OpenAccessResolution:
        return self.resolution


class StaticFetcher:
    def __init__(self, result: PdfFetchResult | Exception) -> None:
        self.result = result

    async def fetch(self, candidate: OpenAccessCandidate) -> PdfFetchResult:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


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


def record(*, abstract: str | None) -> PaperRecord:
    provenance = SourceProvenance(
        source="evidence_source",
        source_id="10.1000/workflow",
        source_url="https://example.test/workflow",
        raw_hash="a" * 64,
    )
    return PaperRecord(
        title="Evidence Workflow for Future Alerts",
        abstract=abstract,
        publication_year=2026,
        doi="10.1000/workflow",
        arxiv_id="2401.12345v2",
        source_urls=["https://example.test/workflow"],
        source_provenance=[provenance],
        abstract_provenance=provenance if abstract else None,
    )


def create_paper(client: TestClient, headers: dict[str, str], adapter: EvidenceAdapter) -> int:
    client.app.state.search_service = FederatedSearchService([adapter])
    response = client.post(
        "/api/search/papers",
        headers=headers,
        json={
            "query": "10.1000/workflow",
            "sources": ["evidence_source"],
            "limit": 1,
            "mode": "precise",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["papers"][0]["id"]


def test_restore_workflow_is_scoped_to_paper_account_and_project(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        owner = register(client, "restore-owner@example.invalid")
        stranger = register(client, "restore-other@example.invalid")
        paper_id = create_paper(client, owner, EvidenceAdapter(record(abstract="Material")))
        project = client.post(
            "/api/projects",
            headers=owner,
            json={"name": "Restore fixture", "broad_direction": "Image segmentation"},
        )
        assert project.status_code == 201, project.text
        project_id = project.json()["id"]
        path = f"/api/papers/{paper_id}/evidence-workflows"
        created = client.post(path, headers=owner, json={"project_id": project_id})
        assert created.status_code == 201, created.text
        restored = client.get(path, headers=owner, params={"project_id": project_id})
        assert restored.status_code == 200, restored.text
        assert [row["id"] for row in restored.json()] == [created.json()["id"]]
        assert client.get(path, headers=owner).json() == []
        assert client.get(path, headers=stranger).json() == []
        assert (
            client.get(path, headers=stranger, params={"project_id": project_id}).status_code == 404
        )
        assert client.get(path).status_code == 401


def make_pdf() -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(72, 810, "arXiv:2401.12345v2")
    canvas.drawString(72, 760, "Method")
    canvas.drawString(72, 735, "We rank future anomaly risk using causal windows.")
    canvas.save()
    return buffer.getvalue()


def candidate() -> OpenAccessCandidate:
    return OpenAccessCandidate(
        source="openalex",
        source_record_id="W1",
        landing_url="https://repository.example/item/1",
        pdf_url="https://repository.example/item/1.pdf",
        license="cc-by",
        normalized_license="cc-by",
        host_type="repository",
        version="acceptedVersion",
        is_oa=True,
        access_decision="auto_ingest",
        provenance_hash="b" * 64,
    )


def test_workflow_create_run_read_and_cross_user_denial(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    adapter = EvidenceAdapter(record(abstract=None))
    with TestClient(app) as client:
        owner = register(client, "workflow-owner@example.com")
        stranger = register(client, "workflow-stranger@example.com")
        paper_id = create_paper(client, owner, adapter)
        adapter.record = record(abstract="We introduce an audited future-alert workflow.")
        app.state.oa_resolver = StaticResolver(OpenAccessResolution())

        created = client.post(
            f"/api/papers/{paper_id}/evidence-workflows",
            headers=owner,
            json={"sources": ["evidence_source"], "allow_oa_fulltext": True},
        )
        assert created.status_code == 201, created.text
        job = created.json()
        assert job["status"] == "pending"
        assert (
            client.get(f"/api/evidence-workflows/{job['id']}", headers=stranger).status_code == 404
        )

        run = client.post(f"/api/evidence-workflows/{job['id']}/run", headers=owner)
        assert run.status_code == 200, run.text
        payload = run.json()
        assert payload["status"] == "partial"
        assert payload["strongest_evidence"] == "abstract_only"
        event_types = [item["event_type"] for item in payload["events"]]
        assert event_types[:4] == [
            "created",
            "started",
            "identity_resolution",
            "abstract_acquisition",
        ]
        assert event_types[-1] == "partial"
        assert payload["result"]["analysis_id"] > 0


def test_workflow_ingests_permitted_oa_pdf_and_finishes(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    adapter = EvidenceAdapter(record(abstract="Verified abstract."))
    pdf = make_pdf()
    fetched = PdfFetchResult(
        final_url="https://repository.example/item/1.pdf",
        data=pdf,
        sha256=__import__("hashlib").sha256(pdf).hexdigest(),
        size_bytes=len(pdf),
        content_type="application/pdf",
        response_hash="c" * 64,
        retrieved_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    with TestClient(app) as client:
        headers = register(client, "workflow-oa@example.com")
        paper_id = create_paper(client, headers, adapter)
        app.state.oa_resolver = StaticResolver(
            OpenAccessResolution(candidates=[candidate()], selected=candidate())
        )
        app.state.pdf_fetcher = StaticFetcher(fetched)
        job = client.post(
            f"/api/papers/{paper_id}/evidence-workflows",
            headers=headers,
            json={"sources": ["evidence_source"], "allow_oa_fulltext": True},
        ).json()

        completed = client.post(f"/api/evidence-workflows/{job['id']}/run", headers=headers)
        assert completed.status_code == 200, completed.text
        body = completed.json()
        assert body["status"] == "succeeded"
        assert body["strongest_evidence"] == "open_fulltext"
        assert body["result"]["document_id"] > 0
        assert any(event["event_type"] == "pdf_parse_and_index" for event in body["events"])
        documents = client.get(f"/api/papers/{paper_id}/documents", headers=headers).json()
        assert documents[0]["source_type"] == "open_access_repository"


def test_workflow_external_pdf_failure_preserves_abstract_and_reports_reason(
    tmp_path: Path,
) -> None:
    app = create_app(settings_for(tmp_path))
    adapter = EvidenceAdapter(record(abstract="Verified abstract before OA failure."))
    with TestClient(app) as client:
        headers = register(client, "workflow-failure@example.com")
        paper_id = create_paper(client, headers, adapter)
        app.state.oa_resolver = StaticResolver(
            OpenAccessResolution(candidates=[candidate()], selected=candidate())
        )
        app.state.pdf_fetcher = StaticFetcher(httpx.ConnectError("repository offline"))
        job = client.post(
            f"/api/papers/{paper_id}/evidence-workflows",
            headers=headers,
            json={"sources": ["evidence_source"], "allow_oa_fulltext": True},
        ).json()

        completed = client.post(f"/api/evidence-workflows/{job['id']}/run", headers=headers).json()
        assert completed["status"] == "partial"
        assert completed["strongest_evidence"] == "abstract_only"
        assert "repository offline" in " ".join(completed["result"]["warnings"])
        assert completed["result"]["analysis_id"] > 0


def test_success_without_durable_result_is_not_verified(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = register(client, "missing-result@example.com")
        paper_id = create_paper(client, headers, EvidenceAdapter(record(abstract=None)))
        job = client.post(
            f"/api/papers/{paper_id}/evidence-workflows", headers=headers, json={}
        ).json()
        with app.state.database.session() as session:
            row = session.get(Job, job["id"])
            assert row is not None
            row.status = "succeeded"
            session.commit()
        response = client.get(f"/api/evidence-workflows/{job['id']}", headers=headers)
        assert response.status_code == 200
        assert response.json()["result_integrity"] == "missing_or_mismatched"


def test_workflow_cancel_uses_terminal_semantics(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    adapter = EvidenceAdapter(record(abstract=None))
    with TestClient(app) as client:
        headers = register(client, "workflow-cancel@example.com")
        paper_id = create_paper(client, headers, adapter)
        job = client.post(
            f"/api/papers/{paper_id}/evidence-workflows",
            headers=headers,
            json={},
        ).json()
        cancelled = client.post(f"/api/evidence-workflows/{job['id']}/cancel", headers=headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["terminal"] is True
        assert (
            client.post(f"/api/evidence-workflows/{job['id']}/run", headers=headers).status_code
            == 409
        )


def test_workflow_refreshes_author_and_dataset_cards_after_analysis(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    rich_record = record(
        abstract=(
            "We introduce a causal time-series anomaly ranking method and evaluate it on "
            "SWaT using PR-AUC."
        )
    )
    rich_record.authors = [
        __import__("research_navigator.scholarly.base", fromlist=["PaperAuthor"]).PaperAuthor(
            name="Ada Researcher",
            orcid="0000-0002-1825-0097",
            affiliations=["Evidence Lab"],
        )
    ]
    adapter = EvidenceAdapter(rich_record)
    with TestClient(app) as client:
        headers = register(client, "workflow-cards@example.com")
        paper_id = create_paper(client, headers, adapter)
        app.state.oa_resolver = StaticResolver(OpenAccessResolution())
        job = client.post(
            f"/api/papers/{paper_id}/evidence-workflows",
            headers=headers,
            json={"sources": ["evidence_source"], "allow_oa_fulltext": False},
        ).json()

        completed = client.post(f"/api/evidence-workflows/{job['id']}/run", headers=headers)
        assert completed.status_code == 200, completed.text
        body = completed.json()
        author_event = next(
            item for item in body["events"] if item["event_type"] == "author_card_refresh"
        )
        dataset_event = next(
            item for item in body["events"] if item["event_type"] == "dataset_card_refresh"
        )
        assert author_event["detail"]["outcome"] == "succeeded"
        assert author_event["detail"]["count"] == 1
        assert dataset_event["detail"]["outcome"] == "succeeded"
        assert dataset_event["detail"]["count"] == 1
        assert (
            client.get(f"/api/papers/{paper_id}/authors", headers=headers).json()[0][
                "canonical_name"
            ]
            == "Ada Researcher"
        )
        assert (
            client.get(f"/api/papers/{paper_id}/datasets", headers=headers).json()[0][
                "canonical_name"
            ]
            == "SWaT"
        )
