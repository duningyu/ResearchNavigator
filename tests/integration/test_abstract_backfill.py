from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.models import Paper, PaperAnalysisRecord, PaperSource, User
from research_navigator.scholarly.base import (
    AdapterSearchResult,
    PaperRecord,
    ScholarlyAdapter,
    SearchRequest,
    SourceProvenance,
    SourceStatus,
)
from research_navigator.scholarly.service import FederatedSearchService


class BackfillAdapter(ScholarlyAdapter):
    name = "backfill_source"
    supports_evidence_acquisition = True

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        provenance = SourceProvenance(
            source=self.name,
            source_id="10.1000/legacy",
            source_url="https://example.test/legacy",
            raw_hash="f" * 64,
        )
        return AdapterSearchResult(
            records=[
                PaperRecord(
                    title="Legacy Abstract Provenance",
                    abstract="A trusted reacquired abstract for future warning research.",
                    publication_year=2024,
                    doi="10.1000/legacy",
                    source_provenance=[provenance],
                    abstract_provenance=provenance,
                )
            ],
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


def register(client: TestClient, email: str) -> tuple[dict[str, str], int]:
    payload = client.post(
        "/api/auth/register",
        json={"email": email, "password": "research-pass-123", "display_name": "Admin"},
    ).json()
    return {"Authorization": f"Bearer {payload['access_token']}"}, payload["user"]["id"]


def make_admin(app, user_id: int) -> None:
    with app.state.database.session() as session:
        user = session.get(User, user_id)
        user.is_admin = True
        session.commit()


def seed_legacy(app) -> int:
    with app.state.database.session() as session:
        paper = Paper(
            title="Legacy Abstract Provenance",
            normalized_title="legacy abstract provenance",
            abstract="Old summary without trustworthy provenance.",
            publication_year=2024,
            doi="10.1000/legacy",
        )
        session.add(paper)
        session.flush()
        session.add(
            PaperSource(
                paper_id=paper.id,
                source="legacy_import",
                source_id="legacy-1",
                provides_abstract=False,
                is_fixture=False,
            )
        )
        session.commit()
        return paper.id


def test_backfill_is_admin_only_and_dry_run_does_not_promote(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers, user_id = register(client, "backfill-user@example.com")
        seed_legacy(app)
        denied = client.post(
            "/api/admin/backfills/abstract-provenance",
            headers=headers,
            json={"dry_run": True, "sources": ["backfill_source"]},
        )
        assert denied.status_code == 403
        make_admin(app, user_id)
        app.state.search_service = FederatedSearchService([BackfillAdapter()])
        job = client.post(
            "/api/admin/backfills/abstract-provenance",
            headers=headers,
            json={"dry_run": True, "sources": ["backfill_source"]},
        ).json()
        result = client.post(f"/api/admin/backfills/{job['id']}/run", headers=headers)
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["result"]["counts"]["would_verify"] == 1
        with app.state.database.session() as session:
            assert session.scalar(
                select(PaperSource.id).where(PaperSource.provides_abstract.is_(True))
            ) is None
            assert session.scalar(select(PaperAnalysisRecord.id)) is None


def test_backfill_exact_doi_promotes_reanalyzes_and_is_idempotent(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers, user_id = register(client, "backfill-admin@example.com")
        make_admin(app, user_id)
        paper_id = seed_legacy(app)
        app.state.search_service = FederatedSearchService([BackfillAdapter()])
        first = client.post(
            "/api/admin/backfills/abstract-provenance",
            headers=headers,
            json={"dry_run": False, "sources": ["backfill_source"], "batch_size": 25},
        ).json()
        finished = client.post(f"/api/admin/backfills/{first['id']}/run", headers=headers).json()
        assert finished["status"] == "succeeded"
        assert finished["result"]["counts"]["verified_and_updated"] == 1
        with app.state.database.session() as session:
            paper = session.get(Paper, paper_id)
            assert paper.abstract.startswith("A trusted reacquired")
            assert session.scalar(
                select(PaperSource.id).where(
                    PaperSource.paper_id == paper_id,
                    PaperSource.provides_abstract.is_(True),
                    PaperSource.is_fixture.is_(False),
                )
            )
            assert session.scalar(
                select(PaperAnalysisRecord.id).where(PaperAnalysisRecord.paper_id == paper_id)
            )

        second = client.post(
            "/api/admin/backfills/abstract-provenance",
            headers=headers,
            json={"dry_run": False, "sources": ["backfill_source"]},
        ).json()
        repeated = client.post(
            f"/api/admin/backfills/{second['id']}/run", headers=headers
        ).json()
        assert repeated["result"]["counts"]["already_verified"] == 1
        assert repeated["result"]["counts"].get("verified_and_updated", 0) == 0


def test_backfill_job_can_be_cancelled_before_execution(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers, user_id = register(client, "backfill-cancel@example.com")
        make_admin(app, user_id)
        seed_legacy(app)
        job = client.post(
            "/api/admin/backfills/abstract-provenance", headers=headers, json={}
        ).json()
        cancelled = client.post(
            f"/api/admin/backfills/{job['id']}/cancel", headers=headers
        ).json()
        assert cancelled["status"] == "cancelled"
        assert client.post(
            f"/api/admin/backfills/{job['id']}/run", headers=headers
        ).status_code == 409
