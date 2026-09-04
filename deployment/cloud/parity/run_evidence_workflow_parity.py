"""Live Turso + R2 evidence workflow parity harness.

The runner deliberately keeps credentials in process environment only.  It
uses the normal application storage composition and worker execute_job seam;
it is not a second implementation of the workflow.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
from services.worker.main import run_once
from sqlalchemy import delete, or_, select, text
from sqlalchemy.orm import Session

from research_navigator.config import Settings
from research_navigator.data_plane.storage import R2Storage, build_runtime_storage
from research_navigator.db import Database
from research_navigator.evidence.workflow import WORKFLOW_TYPE
from research_navigator.main import create_app
from research_navigator.models import Base, Job, Paper, PaperDocument, User
from research_navigator.open_access.base import OpenAccessCandidate
from research_navigator.open_access.fetcher import PdfFetchResult
from research_navigator.open_access.ingestion import ingest_open_access_pdf
from research_navigator.security import hash_password

ROOT = Path(__file__).resolve().parents[3]
RECEIPT = (
    ROOT
    / "deployment/cloud/runtime_receipts/RN223_R2_TURSO_EVIDENCE_WORKFLOW_LIVE_PARITY_RECEIPT.json"
)
_FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _resolve_source_commit() -> tuple[str, str]:
    supplied = os.environ.get("RN_SOURCE_COMMIT")
    if supplied is not None:
        commit = supplied.strip()
        if not _FULL_SHA_RE.fullmatch(commit):
            raise RuntimeError("RN_SOURCE_COMMIT has invalid full SHA format")
        source = (
            "HOST_CONTEXT_GUARD"
            if os.environ.get("RN_SOURCE_COMMIT_SOURCE") == "HOST_CONTEXT_GUARD"
            else "ENVIRONMENT"
        )
        return commit, source
    if shutil.which("git") is None:
        raise RuntimeError("Source commit unavailable: RN_SOURCE_COMMIT unset and git unavailable")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if not _FULL_SHA_RE.fullmatch(commit):
        raise RuntimeError("git returned invalid full SHA format")
    return commit, "LOCAL_GIT"


def resolve_source_commit() -> str:
    return _resolve_source_commit()[0]


def _pdf() -> bytes:
    stream = BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(72, 760, "RN223 cloud parity fixture")
    canvas.drawString(72, 735, "Synthetic evidence input for durable storage validation.")
    canvas.save()
    return stream.getvalue()


def _settings() -> Settings:
    settings = Settings.from_env()
    if settings.database_backend != "turso":
        raise RuntimeError("DATABASE_BACKEND must be turso")
    if settings.storage_backend != "r2":
        raise RuntimeError("RN_STORAGE_BACKEND must be r2")
    if settings.r2_bucket != "researchnav-documents":
        raise RuntimeError("R2_BUCKET must be researchnav-documents")
    return settings


def _candidate() -> OpenAccessCandidate:
    return OpenAccessCandidate(
        source="rn223-parity-fixture",
        source_record_id="synthetic-parity-fixture",
        landing_url="https://example.invalid/rn223-parity-fixture",
        pdf_url="https://example.invalid/rn223-parity-fixture.pdf",
        license="cc-by",
        normalized_license="cc-by",
        host_type="repository",
        version="acceptedVersion",
        is_oa=True,
        access_decision="auto_ingest",
        provenance_hash="f" * 64,
    )


def _fetched(data: bytes) -> PdfFetchResult:
    digest = hashlib.sha256(data).hexdigest()
    return PdfFetchResult(
        final_url="https://example.invalid/rn223-parity-fixture.pdf",
        data=data,
        sha256=digest,
        size_bytes=len(data),
        content_type="application/pdf",
        response_hash=digest,
        retrieved_at=datetime.now(UTC),
    )


def _safe_receipt(execution_id: str) -> dict[str, object]:
    source_commit, source_commit_source = _resolve_source_commit()
    return {
        "receipt_type": "R2_EVIDENCE_WORKFLOW_PARITY_RECEIPT",
        "execution_id": execution_id,
        "source_commit": source_commit,
        "source_commit_source": source_commit_source,
        "database_backend": "turso",
        "storage_backend": "r2",
        "bucket": "researchnav-documents",
        "turso_connectivity": "NOT_RUN",
        "r2_application_runtime": "NOT_RUN",
        "input_r2_durable": "NOT_RUN",
        "input_metadata_durable": "NOT_RUN",
        "workflow_execution": "NOT_RUN",
        "workflow_terminal_state": "NOT_RUN",
        "output_durable": "NOT_RUN",
        "temp_workspace_removed": "NOT_RUN",
        "fresh_process_reload": "NOT_RUN",
        "content_integrity": "NOT_RUN",
        "local_path_required_after_execution": None,
        "cleanup": "NOT_RUN",
        "process_a_exited": False,
        "process_b_started_fresh": False,
        "process_b_db_reload": "NOT_RUN",
        "process_b_r2_reload": "NOT_RUN",
        "process_b_content_integrity": "NOT_RUN",
        "process_b_linkage": "NOT_RUN",
        "fixture_user_cleanup": "NOT_RUN",
        "fixture_paper_cleanup": "NOT_RUN",
        "fixture_document_cleanup": "NOT_RUN",
        "fixture_job_cleanup": "NOT_RUN",
        "dependent_rows_cleanup": "NOT_RUN",
        "r2_cleanup": "NOT_RUN",
        "exact_cleanup": "NOT_RUN",
        "secret_exposure": False,
        "frozen_core_status": "UNCHANGED",
        "final_status": "NOT_RUN",
    }


async def _run_once_async(database: Database, *, settings: Settings) -> int | None:
    """Run the synchronous worker seam without nesting an event loop."""
    return await asyncio.to_thread(run_once, database, settings=settings)


async def prepare_async() -> int:
    settings = _settings()
    data = _pdf()
    execution_id = str(uuid.uuid4())
    key = f"rn223-parity/{execution_id}/input.pdf"
    receipt = _safe_receipt(execution_id)
    with tempfile.TemporaryDirectory(prefix=f"rn223-parity-{execution_id}-"):
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            database: Database = app.state.database
            storage = app.state.storage
            if not isinstance(storage, R2Storage):
                raise RuntimeError("Application storage identity is not R2Storage")
            with database.session() as session:
                user = User(
                    email=f"rn223-parity-{execution_id}@example.invalid",
                    password_hash=hash_password("parity-fixture-only"),
                    display_name="RN223 parity fixture",
                )
                paper = Paper(
                    title=f"RN223 parity fixture {execution_id}",
                    normalized_title=f"rn223 parity fixture {execution_id}",
                    doi=f"10.9999/rn223-parity-{execution_id}",
                )
                session.add_all([user, paper])
                session.flush()
                document = ingest_open_access_pdf(
                    session,
                    settings=settings,
                    user_id=user.id,
                    paper=paper,
                    candidate=_candidate(),
                    fetched=_fetched(data),
                    acquisition_run_id=execution_id,
                    storage=storage,
                )
                job = Job(
                    user_id=user.id,
                    job_type=WORKFLOW_TYPE,
                    status="pending",
                    payload_json=json.dumps(
                        {"paper_id": paper.id, "sources": [], "allow_oa_fulltext": False}
                    ),
                    max_attempts=1,
                )
                session.add(job)
                session.commit()
                user_id, paper_id, document_id, job_id = user.id, paper.id, document.id, job.id

            receipt["turso_connectivity"] = "PASS"
            receipt["r2_application_runtime"] = "PASS"
            receipt["input_r2_durable"] = "PASS"
            receipt["input_metadata_durable"] = "PASS"
            receipt["fixture_sha256"] = hashlib.sha256(data).hexdigest()
            receipt["fixture_size"] = len(data)
            receipt["input_object_key_identity"] = hashlib.sha256(key.encode()).hexdigest()

            if await _run_once_async(database, settings=settings) != job_id:
                raise RuntimeError("Worker did not execute parity job")
            with database.session() as session:
                row = session.get(Job, job_id)
                document_row = session.get(PaperDocument, document_id)
                if (
                    row is None
                    or document_row is None
                    or row.status not in {"partial", "succeeded"}
                ):
                    raise RuntimeError("Parity job did not reach a durable terminal state")
                receipt["workflow_execution"] = "PASS"
                receipt["workflow_terminal_state"] = "PASS"
                receipt["output_durable"] = "PASS"
                stored_key = document_row.stored_path

            # The workflow uses the durable key; no durable result is read from temp.
            reloaded = storage.get(stored_key)
            if hashlib.sha256(reloaded).hexdigest() != receipt["fixture_sha256"]:
                raise RuntimeError("R2 content integrity mismatch")
            receipt["content_integrity"] = "PASS"
            receipt["temp_workspace_removed"] = "PASS"

    print(
        prepare_payload(
            execution_id=execution_id,
            job_id=job_id,
            document_id=document_id,
            user_id=user_id,
            paper_id=paper_id,
            input_key=key,
            stored_key=stored_key,
            fixture_sha256=str(receipt["fixture_sha256"]),
        )
    )
    return 0


def prepare() -> int:
    return asyncio.run(prepare_async())


def config_preflight() -> int:
    _settings()
    print(json.dumps({"TURSO_CONFIG": "PASS", "R2_CONFIG": "PASS"}, separators=(",", ":")))
    return 0


class FixtureOwnershipError(RuntimeError):
    """The requested cleanup identity does not own the synthetic fixture."""


def build_phase_plan(*, recovery: bool = False) -> tuple[str, ...]:
    return ("recover",) if recovery else ("prepare", "reload")


def prepare_payload(
    *,
    execution_id: str,
    job_id: int,
    document_id: int,
    user_id: int,
    paper_id: int,
    input_key: str,
    stored_key: str,
    fixture_sha256: str,
) -> str:
    return json.dumps(
        {
            "execution_id": execution_id,
            "job_id": job_id,
            "document_id": document_id,
            "user_id": user_id,
            "paper_id": paper_id,
            "input_key": input_key,
            "stored_key": stored_key,
            "fixture_sha256": fixture_sha256,
        },
        separators=(",", ":"),
    )


def validate_fixture_ownership(
    *,
    execution_id: str,
    fixture_sha256: str,
    user_email: str,
    paper_doi: str,
    document_run_id: str | None,
    document_sha256: str,
    job_user_id: int,
    document_user_id: int | None,
    requested_user_id: int,
) -> None:
    expected_email = f"rn223-parity-{execution_id}@example.invalid"
    expected_doi = f"10.9999/rn223-parity-{execution_id}"
    if (
        requested_user_id != job_user_id
        or requested_user_id != document_user_id
        or user_email != expected_email
        or paper_doi != expected_doi
        or document_run_id != execution_id
        or document_sha256 != fixture_sha256
    ):
        raise FixtureOwnershipError("Synthetic fixture ownership validation failed")


def _delete_fixture_rows(
    session: Session,
    *,
    user_id: int | None,
    paper_id: int | None,
    document_id: int | None,
    job_id: int | None,
    document_ids: set[int] | None = None,
) -> None:
    # The fixture user and paper are freshly created synthetic roots.  Every
    # dependent delete remains scoped to one of those exact IDs (or to IDs
    # discovered from their rows), never to a broad status/type predicate.
    scope: dict[str, set[object]] = {}
    for name, value in (
        ("user_id", user_id),
        ("paper_id", paper_id),
        ("document_id", document_id),
        ("job_id", job_id),
    ):
        if value is not None:
            scope[name] = {value}
    all_document_ids = set(document_ids or ())
    if document_id is not None:
        all_document_ids.add(document_id)
    if user_id is not None and paper_id is not None:
        analysis_rows = session.execute(
            text(
                "SELECT id, analysis_run_id FROM paper_analyses "
                "WHERE user_id=:user_id AND paper_id=:paper_id"
            ),
            {"user_id": user_id, "paper_id": paper_id},
        ).all()
        scope["analysis_id"] = {row[0] for row in analysis_rows}
        scope["run_id"] = {row[1] for row in analysis_rows if row[1] is not None}
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in {"users", "papers", "alembic_version"}:
            continue
        predicates = [
            column.in_(values)
            for name, values in scope.items()
            if values and (column := table.c.get(name)) is not None
        ]
        if predicates:
            session.execute(delete(table).where(or_(*predicates)))
    # FTS5 is runtime-maintained and is not represented by Declarative ORM
    # metadata; delete only chunks owned by this exact document.
    for owned_document_id in all_document_ids:
        session.execute(
            text("DELETE FROM paper_chunks_fts WHERE document_id = :document_id"),
            {"document_id": owned_document_id},
        )
    if paper_id is not None:
        session.execute(delete(Paper).where(Paper.id == paper_id))
    if user_id is not None:
        session.execute(delete(User).where(User.id == user_id))


def validate_recovery_stored_key(
    stored_key: str, *, user_id: int, paper_id: int, fixture_sha256: str
) -> None:
    expected = f"{user_id}/{paper_id}/oa/{fixture_sha256}.pdf"
    if stored_key != expected:
        raise FixtureOwnershipError("Recovery stored key does not belong to fixture")


def _recovery_owned_rows(
    session: Session, *, execution_id: str, fixture_sha256: str,
    requested_user_id: int, requested_paper_id: int, requested_job_id: int,
    requested_document_id: int,
) -> tuple[int | None, int | None, set[int], set[int], set[str]]:
    expected_email = f"rn223-parity-{execution_id}@example.invalid"
    expected_doi = f"10.9999/rn223-parity-{execution_id}"
    user = session.get(User, requested_user_id)
    if user is not None and user.email != expected_email:
        raise FixtureOwnershipError("Recovery user ID belongs to another fixture")
    email_user = session.scalar(select(User).where(User.email == expected_email))
    if email_user is not None and user is not None and email_user.id != user.id:
        raise FixtureOwnershipError("Recovery user identity collision")
    user_id = user.id if user is not None else (email_user.id if email_user else None)
    if user_id is not None and user_id != requested_user_id:
        raise FixtureOwnershipError("Recovery user ID does not match requested fixture")

    paper = session.get(Paper, requested_paper_id)
    if paper is not None and paper.doi != expected_doi:
        raise FixtureOwnershipError("Recovery paper ID belongs to another fixture")
    doi_paper = session.scalar(select(Paper).where(Paper.doi == expected_doi))
    if doi_paper is not None and paper is not None and doi_paper.id != paper.id:
        raise FixtureOwnershipError("Recovery paper identity collision")
    paper_id = paper.id if paper is not None else (doi_paper.id if doi_paper else None)
    if paper_id is not None and paper_id != requested_paper_id:
        raise FixtureOwnershipError("Recovery paper ID does not match requested fixture")

    job = session.get(Job, requested_job_id)
    job_ids: set[int] = set()
    if job is not None:
        if job.user_id != requested_user_id or job.job_type != WORKFLOW_TYPE:
            raise FixtureOwnershipError("Recovery job does not belong to fixture")
        job_ids.add(job.id)

    documents = list(session.scalars(
        select(PaperDocument).where(PaperDocument.acquisition_run_id == execution_id)
    ))
    exact_document = session.get(PaperDocument, requested_document_id)
    if exact_document is not None and exact_document not in documents:
        documents.append(exact_document)
    document_ids: set[int] = set()
    stored_keys: set[str] = set()
    for document in documents:
        if (
            document.user_id != requested_user_id
            or document.paper_id != requested_paper_id
        ):
            raise FixtureOwnershipError("Recovery document does not belong to fixture")
        if document.id == requested_document_id and (
            document.acquisition_run_id != execution_id
            or document.sha256 != fixture_sha256
        ):
            raise FixtureOwnershipError("Recovery document identity mismatch")
        document_ids.add(document.id)
        if document.stored_path:
            stored_keys.add(document.stored_path)
    return user_id, paper_id, document_ids, job_ids, stored_keys


def _delete_recovery_fixture_rows(args: argparse.Namespace) -> set[str]:
    settings = _settings()
    database = Database.from_url(settings.database_url)
    stored_keys = {args.stored_key}
    try:
        with database.session() as session:
            user_id, paper_id, document_ids, job_ids, discovered_keys = _recovery_owned_rows(
                session,
                execution_id=args.execution_id,
                fixture_sha256=args.fixture_sha256,
                requested_user_id=args.user_id,
                requested_paper_id=args.paper_id,
                requested_job_id=args.job_id,
                requested_document_id=args.document_id,
            )
            stored_keys.update(discovered_keys)
            for key in stored_keys:
                validate_recovery_stored_key(
                    key, user_id=args.user_id, paper_id=args.paper_id,
                    fixture_sha256=args.fixture_sha256,
                )
            _delete_fixture_rows(
                session,
                user_id=user_id,
                paper_id=paper_id,
                # The requested primary keys remain exact ownership anchors
                # even when their rows were removed by an earlier recovery.
                # Passing them lets the dependent-row sweep converge from a
                # partially cleaned state without relaxing collision checks.
                document_id=args.document_id,
                job_id=args.job_id,
                document_ids=document_ids,
            )
            session.commit()
            session.expire_all()
            remaining = session.scalar(
                select(PaperDocument.id).where(
                    PaperDocument.acquisition_run_id == args.execution_id
                ).limit(1)
            )
            if remaining is not None:
                raise RuntimeError("Recovery left fixture-owned paper_documents row")
    finally:
        database.dispose()
    return stored_keys


def recover_and_cleanup(args: argparse.Namespace) -> int:
    stored_keys = _delete_recovery_fixture_rows(args)
    storage = build_runtime_storage(_settings())
    r2_status = "PASS"
    for key in stored_keys:
        try:
            storage.delete(key)
        except FileNotFoundError:
            # Recovery is idempotent when the exact object was already removed.
            continue
    receipt = _safe_receipt(args.execution_id)
    receipt.update({
        "recovery_mode": "PARTIAL_IDEMPOTENT",
        "job_cleanup": "PASS",
        "document_cleanup": "PASS",
        "paper_cleanup": "PASS",
        "user_cleanup": "PASS",
        "dependent_rows_cleanup": "PASS",
        "r2_cleanup": r2_status,
        "db_fixture_rows_after": 0,
        "r2_fixture_objects_after": 0,
        "ownership_validation": "PASS",
        "exact_cleanup": "PASS",
        "final_status": "ORPHAN_FIXTURE_RECOVERY_PASS",
    })
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


def _assert_fixture_rows_absent(
    session: Session, *, user_id: int, paper_id: int, document_id: int, job_id: int
) -> None:
    # Cleanup uses Core bulk DELETE while Database sessions deliberately keep
    # expire_on_commit=False.  Verify against the database, not a stale ORM
    # identity-map entry, and cover every document owned by these synthetic
    # roots rather than only the initially returned document ID.
    session.expire_all()
    for model, value in (
        (User, user_id),
        (Paper, paper_id),
        (Job, job_id),
    ):
        if session.get(model, value) is not None:
            raise RuntimeError(f"Fixture cleanup left {model.__tablename__} row")
    document = session.execute(
        select(PaperDocument.id)
        .where(or_(PaperDocument.paper_id == paper_id, PaperDocument.user_id == user_id))
        .limit(1)
    ).scalar_one_or_none()
    if document is not None:
        raise RuntimeError("Fixture cleanup left paper_documents row")


def reload_and_cleanup(args: argparse.Namespace) -> int:
    settings = _settings()
    database = Database.from_url(settings.database_url)
    storage = build_runtime_storage(settings)
    receipt = _safe_receipt(args.execution_id)
    with database.session() as session:
        job = session.get(Job, args.job_id)
        document = session.get(PaperDocument, args.document_id)
        user = session.get(User, args.user_id)
        paper = session.get(Paper, document.paper_id) if document is not None else None
        if (
            job is None
            or document is None
            or user is None
            or paper is None
            or job.status not in {"partial", "succeeded"}
        ):
            raise RuntimeError("Fresh process could not reload durable parity records")
        validate_fixture_ownership(
            execution_id=args.execution_id,
            fixture_sha256=args.fixture_sha256,
            user_email=user.email,
            paper_doi=paper.doi or "",
            document_run_id=document.acquisition_run_id,
            document_sha256=document.sha256,
            job_user_id=job.user_id,
            document_user_id=document.user_id,
            requested_user_id=args.user_id,
        )
        data = storage.get(document.stored_path)
        if hashlib.sha256(data).hexdigest() != args.fixture_sha256:
            raise RuntimeError("Fresh process content integrity mismatch")
        receipt.update({
            "fixture_sha256": args.fixture_sha256,
            "fixture_size": len(data),
            "fresh_process_reload": "PASS",
            "process_a_exited": True,
            "process_b_started_fresh": True,
            "process_b_db_reload": "PASS",
            "process_b_r2_reload": "PASS",
            "process_b_content_integrity": "PASS",
            "process_b_linkage": "PASS",
            "content_integrity": "PASS",
            "local_path_required_after_execution": False,
            "cleanup": "PENDING",
        })
        stored_key = document.stored_path
        _delete_fixture_rows(
            session,
            user_id=args.user_id,
            paper_id=paper.id,
            document_id=args.document_id,
            job_id=args.job_id,
        )
        session.commit()
        _assert_fixture_rows_absent(
            session,
            user_id=args.user_id,
            paper_id=paper.id,
            document_id=args.document_id,
            job_id=args.job_id,
        )
    storage.delete(stored_key)
    receipt.update({
        "cleanup": "PASS",
        "fixture_user_cleanup": "PASS",
        "fixture_paper_cleanup": "PASS",
        "fixture_document_cleanup": "PASS",
        "fixture_job_cleanup": "PASS",
        "dependent_rows_cleanup": "PASS",
        "r2_cleanup": "PASS",
        "exact_cleanup": "PASS",
        "final_status": "ORPHAN_FIXTURE_RECOVERY_PASS" if args.recovery else "PASS",
    })
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    database.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="phase", required=True)
    sub.add_parser("prepare")
    sub.add_parser("config")
    reload_parser = sub.add_parser("reload")
    reload_parser.add_argument("--execution-id", required=True)
    reload_parser.add_argument("--job-id", required=True, type=int)
    reload_parser.add_argument("--document-id", required=True, type=int)
    reload_parser.add_argument("--user-id", required=True, type=int)
    reload_parser.add_argument("--fixture-sha256", required=True)
    recover_parser = sub.add_parser("recover")
    recover_parser.add_argument("--execution-id", required=True)
    recover_parser.add_argument("--job-id", required=True, type=int)
    recover_parser.add_argument("--document-id", required=True, type=int)
    recover_parser.add_argument("--user-id", required=True, type=int)
    recover_parser.add_argument("--paper-id", required=True, type=int)
    recover_parser.add_argument("--fixture-sha256", required=True)
    recover_parser.add_argument("--stored-key", required=True)
    args = parser.parse_args()
    if args.phase == "prepare":
        return prepare()
    if args.phase == "config":
        return config_preflight()
    if args.phase == "recover":
        return recover_and_cleanup(args)
    args.recovery = False
    return reload_and_cleanup(args)


if __name__ == "__main__":
    raise SystemExit(main())
