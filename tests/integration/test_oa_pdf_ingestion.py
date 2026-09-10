from __future__ import annotations

from io import BytesIO
from pathlib import Path

import httpx
import pytest
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import func, select

from research_navigator.analysis.service import accessible_text, run_paper_analysis
from research_navigator.config import Settings
from research_navigator.db import Database
from research_navigator.documents.index import search_document_chunks
from research_navigator.gaps.matrix import build_evidence_matrix
from research_navigator.models import Paper, PaperChunk, PaperDocument, User
from research_navigator.open_access.base import OpenAccessCandidate
from research_navigator.open_access.fetcher import SafePdfFetcher
from research_navigator.open_access.ingestion import ingest_open_access_pdf
from research_navigator.security import hash_password


def make_pdf(*, partial: bool = False, identity_confirmed: bool = True) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer)
    if identity_confirmed:
        canvas.drawString(72, 790, "arXiv:2401.12345v2")
    canvas.drawString(72, 760, "Method")
    canvas.drawString(72, 735, "We rank future anomaly risk using causal windows.")
    if partial:
        canvas.showPage()
        canvas.showPage()
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


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("identity_confirmed", [False, True])
async def test_permitted_oa_pdf_reuses_parser_and_persists_provenance(
    tmp_path: Path, partial: bool, identity_confirmed: bool
) -> None:
    settings = settings_for(tmp_path)
    settings.ensure_directories()
    database = Database.from_url(settings.database_url)
    database.init()
    pdf = make_pdf(partial=partial, identity_confirmed=identity_confirmed)

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
            arxiv_id="2401.12345v2",
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

        assert document.evidence_level == ("partial_fulltext" if partial else "open_fulltext")
        assert document.source_type == "open_access_repository"
        assert document.source_url == candidate.pdf_url
        assert document.source_record_id == "W1"
        assert document.rights_basis == "explicit_open_license"
        assert document.license == "cc-by"
        assert document.response_hash == fetched.response_hash
        assert document.acquisition_run_id == "run-oa-1"
        assert document.parse_status == ("partial" if partial else "succeeded")
        text, level, _, _ = accessible_text(session, user_id=user.id, paper=paper)
        if not identity_confirmed:
            assert level == "metadata_only", "Unbound PDF must not replace paper evidence"
            assert not search_document_chunks(
                session, user_id=user.id, paper_id=paper.id, query="future anomaly", top_k=3,
            ), "Unbound material must not bypass analysis through retrieval"
            return
        assert "future anomaly" in text
        assert level == document.evidence_level
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
        document.parse_status = "failed"
        session.flush()
        assert not search_document_chunks(
            session, user_id=user.id, paper_id=paper.id, query="future anomaly", top_k=3,
        ), "Failed parse must not expose stale indexed chunks"
        document.parse_status = "partial" if partial else "succeeded"
        session.flush()
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
        analysis = run_paper_analysis(session, user_id=user.id, paper_id=paper.id)
        matrix_before = build_evidence_matrix(session, user_id=user.id, paper_ids=[paper.id])[0]
        assert any(
            citation["material_verified"]
            for citations in matrix_before["field_citations"].values()
            for citation in citations
        )
        # A current paper version change must invalidate the old analysis's PDF evidence,
        # even though its chunk IDs, bytes and extracted text have not changed.
        paper.arxiv_id = "2401.12345v3"
        session.commit()
        matrix_after = build_evidence_matrix(session, user_id=user.id, paper_ids=[paper.id])[0]
        assert matrix_after["material_fingerprint"] != matrix_before["material_fingerprint"]
        assert not any(
            citation["material_verified"]
            for citations in matrix_after["field_citations"].values()
            for citation in citations
        ), "Old material citations must not authorize current candidates or confirmations"
        assert analysis.id is not None  # history retained, not silently rewritten
    database.dispose()
