from __future__ import annotations

from io import BytesIO
from pathlib import Path

import httpx
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import func, select

from research_navigator.config import Settings
from research_navigator.db import Database
from research_navigator.documents.index import search_document_chunks
from research_navigator.models import Paper, PaperChunk, PaperDocument, User
from research_navigator.open_access.base import OpenAccessCandidate
from research_navigator.open_access.fetcher import SafePdfFetcher
from research_navigator.open_access.ingestion import ingest_open_access_pdf
from research_navigator.security import hash_password


def make_pdf() -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(72, 760, "Method")
    canvas.drawString(72, 735, "We rank future anomaly risk using causal windows.")
    canvas.save()
    return buffer.getvalue()


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


async def public_resolver(hostname: str) -> list[str]:
    return ["93.184.216.34"]


async def test_permitted_oa_pdf_reuses_parser_and_persists_provenance(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    settings.ensure_directories()
    database = Database.from_url(settings.database_url)
    database.init()
    pdf = make_pdf()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=pdf)

    candidate = OpenAccessCandidate(
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
        provenance_hash="a" * 64,
    )
    fetched = await SafePdfFetcher(
        max_bytes=settings.max_pdf_bytes,
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    ).fetch(candidate)

    with database.session() as session:
        user = User(
            email="oa@example.com",
            password_hash=hash_password("research-pass-123"),
            display_name="OA User",
        )
        paper = Paper(
            title="OA Paper",
            normalized_title="oa paper",
            doi="10.1000/oa",
        )
        session.add_all([user, paper])
        session.flush()

        document = ingest_open_access_pdf(
            session,
            settings=settings,
            user_id=user.id,
            paper=paper,
            candidate=candidate,
            fetched=fetched,
            acquisition_run_id="run-oa-1",
        )
        session.commit()

        assert document.evidence_level == "open_fulltext"
        assert document.source_type == "open_access_repository"
        assert document.source_url == candidate.pdf_url
        assert document.source_record_id == "W1"
        assert document.rights_basis == "explicit_open_license"
        assert document.license == "cc-by"
        assert document.response_hash == fetched.response_hash
        assert document.acquisition_run_id == "run-oa-1"
        assert document.parse_status == "succeeded"
        assert session.scalar(
            select(func.count(PaperChunk.id)).where(PaperChunk.document_id == document.id)
        )
        hits = search_document_chunks(
            session,
            user_id=user.id,
            paper_id=paper.id,
            query="future anomaly risk",
            top_k=3,
        )
        assert hits
        duplicate = ingest_open_access_pdf(
            session,
            settings=settings,
            user_id=user.id,
            paper=paper,
            candidate=candidate,
            fetched=fetched,
            acquisition_run_id="run-oa-2",
        )
        assert duplicate.id == document.id
        assert session.scalar(select(func.count(PaperDocument.id))) == 1
    database.dispose()
