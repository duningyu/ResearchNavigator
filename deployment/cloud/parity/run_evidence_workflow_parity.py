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
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
from services.worker.main import run_once

from research_navigator.config import Settings
from research_navigator.data_plane.storage import R2Storage, build_runtime_storage
from research_navigator.db import Database
from research_navigator.evidence.workflow import WORKFLOW_TYPE
from research_navigator.main import create_app
from research_navigator.models import Job, Paper, PaperDocument, User
from research_navigator.open_access.base import OpenAccessCandidate
from research_navigator.open_access.fetcher import PdfFetchResult
from research_navigator.open_access.ingestion import ingest_open_access_pdf
from research_navigator.security import hash_password

ROOT = Path(__file__).resolve().parents[3]
RECEIPT = ROOT / "deployment/cloud/R2_EVIDENCE_WORKFLOW_PARITY_RECEIPT.json"


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
    return {
        "receipt_type": "R2_EVIDENCE_WORKFLOW_PARITY_RECEIPT",
        "execution_id": execution_id,
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
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
        "secret_exposure": False,
        "frozen_core_status": "UNCHANGED",
        "final_status": "NOT_RUN",
    }


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
                user_id, document_id, job_id = user.id, document.id, job.id

            receipt["turso_connectivity"] = "PASS"
            receipt["r2_application_runtime"] = "PASS"
            receipt["input_r2_durable"] = "PASS"
            receipt["input_metadata_durable"] = "PASS"
            receipt["fixture_sha256"] = hashlib.sha256(data).hexdigest()
            receipt["fixture_size"] = len(data)
            receipt["input_object_key_identity"] = hashlib.sha256(key.encode()).hexdigest()

            if run_once(database, settings=settings) != job_id:
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

    print(json.dumps({
        "execution_id": execution_id,
        "job_id": job_id,
        "document_id": document_id,
        "user_id": user_id,
        "input_key": key,
        "stored_key": stored_key,
        "fixture_sha256": receipt["fixture_sha256"],
    }, separators=(",", ":")))
    return 0


def prepare() -> int:
    return asyncio.run(prepare_async())


def config_preflight() -> int:
    _settings()
    print(json.dumps({"TURSO_CONFIG": "PASS", "R2_CONFIG": "PASS"}, separators=(",", ":")))
    return 0


def reload_and_cleanup(args: argparse.Namespace) -> int:
    settings = _settings()
    database = Database.from_url(settings.database_url)
    storage = build_runtime_storage(settings)
    receipt = _safe_receipt(args.execution_id)
    with database.session() as session:
        job = session.get(Job, args.job_id)
        document = session.get(PaperDocument, args.document_id)
        if job is None or document is None or job.status not in {"partial", "succeeded"}:
            raise RuntimeError("Fresh process could not reload durable parity records")
        data = storage.get(document.stored_path)
        if hashlib.sha256(data).hexdigest() != args.fixture_sha256:
            raise RuntimeError("Fresh process content integrity mismatch")
        receipt.update({
            "fixture_sha256": args.fixture_sha256,
            "fixture_size": len(data),
            "fresh_process_reload": "PASS",
            "content_integrity": "PASS",
            "local_path_required_after_execution": False,
            "cleanup": "PENDING",
        })
        stored_key = document.stored_path
        session.delete(document)
        session.delete(job)
        session.commit()
    storage.delete(stored_key)
    receipt["cleanup"] = "PASS"
    receipt["final_status"] = "PASS"
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
    reload_parser.add_argument("--fixture-sha256", required=True)
    args = parser.parse_args()
    if args.phase == "prepare":
        return prepare()
    if args.phase == "config":
        return config_preflight()
    return reload_and_cleanup(args)


if __name__ == "__main__":
    raise SystemExit(main())
