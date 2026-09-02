"""Offline Linux parity run using explicit Turso/R2 provider doubles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import cast

from deployment.cloud.parity.offline_provider_doubles import (
    build_offline_database,
    build_offline_storage,
)
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
from services.worker.main import run_once

from research_navigator.config import Settings
from research_navigator.evidence.workflow import WORKFLOW_TYPE
from research_navigator.main import create_app
from research_navigator.models import Job, Paper, PaperDocument, User
from research_navigator.open_access.base import OpenAccessCandidate
from research_navigator.open_access.fetcher import PdfFetchResult
from research_navigator.open_access.ingestion import ingest_open_access_pdf
from research_navigator.security import hash_password

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_NAME = "manifest.json"


def _source_commit() -> str:
    value = os.environ.get("RN_SOURCE_COMMIT", "").strip()
    if len(value) != 40 or any(char not in "0123456789abcdefABCDEF" for char in value):
        raise RuntimeError("RN_SOURCE_COMMIT must be a full commit SHA")
    return value


def _settings(workspace: Path) -> Settings:
    data_dir = workspace / "app-data"
    return Settings(
        data_dir=data_dir,
        database_url="sqlite+pysqlite:///:memory:",
        upload_dir=data_dir / "uploads",
        vector_dir=data_dir / "vectors",
        backup_dir=data_dir / "backups",
        allowed_origins=("http://offline.invalid",),
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
        environment="offline-parity",
    )


def _pdf() -> bytes:
    stream = BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(72, 760, "RN223 offline parity fixture")
    canvas.drawString(72, 735, "Synthetic evidence input; no external provider.")
    canvas.save()
    return stream.getvalue()


def _candidate() -> OpenAccessCandidate:
    return OpenAccessCandidate(
        source="rn223-offline-fixture",
        source_record_id="offline-fixture",
        landing_url="https://offline.invalid/fixture",
        pdf_url="https://offline.invalid/fixture.pdf",
        license="cc-by",
        normalized_license="cc-by",
        host_type="repository",
        version="acceptedVersion",
        is_oa=True,
        access_decision="auto_ingest",
        provenance_hash="a" * 64,
    )


def _fetched(data: bytes) -> PdfFetchResult:
    digest = hashlib.sha256(data).hexdigest()
    return PdfFetchResult(
        final_url="https://offline.invalid/fixture.pdf",
        data=data,
        sha256=digest,
        size_bytes=len(data),
        content_type="application/pdf",
        response_hash=digest,
        retrieved_at=datetime.now(UTC),
    )


def _receipt(execution_id: str, status: str = "NOT_RUN") -> dict[str, object]:
    return {
        "receipt_type": "OFFLINE_PARITY_HARNESS_RECEIPT",
        "execution_id": execution_id,
        "source_commit": _source_commit(),
        "runtime_mode": "OFFLINE_PROVIDER_DOUBLE",
        "cloud_parity_claim": "NOT_A_LIVE_PROVIDER_CLAIM",
        "runtime": "LOCAL_DOCKER_LINUX",
        "network_mode": "none",
        "database_provider": "OFFLINE_TURSO_DOUBLE",
        "storage_provider": "OFFLINE_R2_DOUBLE",
        "database_backend": "explicit_provider_double",
        "storage_backend": "explicit_provider_double",
        "bucket": "researchnav-documents-double",
        "cloud_provider_calls": 0,
        "secret_prompt_count": 0,
        "fixture_provider": "deterministic",
        "workflow_execution": status,
        "workflow_terminal_state": status,
        "temp_workspace_removed": status,
        "fresh_process_reload": status,
        "content_integrity": status,
        "cleanup": status,
        "local_path_required_after_execution": False,
        "secret_exposure": False,
        "frozen_core_status": "UNCHANGED",
        "final_status": status,
    }


def prepare(provider_root: Path, workspace: Path) -> int:
    execution_id = str(uuid.uuid4())
    data = _pdf()
    provider_root.mkdir(parents=True, exist_ok=True)
    storage = build_offline_storage(provider_root)
    database = build_offline_database(provider_root)
    settings = _settings(workspace)
    app = create_app(
        settings,
        database_factory=lambda _settings: database,
        storage_factory=lambda _settings: storage,
    )
    async def seed() -> dict[str, object]:
        async with app.router.lifespan_context(app):
            with database.session() as session:
                user = User(
                    email=f"offline-{execution_id}@offline.invalid",
                    password_hash=hash_password("offline-fixture-only"),
                    display_name="RN223 offline fixture",
                )
                paper = Paper(
                    title=f"RN223 offline parity {execution_id}",
                    normalized_title=f"rn223 offline parity {execution_id}",
                    doi=f"10.9999/offline-{execution_id}",
                )
                session.add_all([user, paper])
                session.flush()
                document = ingest_open_access_pdf(
                    session, settings=settings, user_id=user.id, paper=paper,
                    candidate=_candidate(), fetched=_fetched(data),
                    acquisition_run_id=execution_id, storage=storage,
                )
                job = Job(
                    user_id=user.id, job_type=WORKFLOW_TYPE, status="pending",
                    payload_json=json.dumps({
                        "paper_id": paper.id, "sources": [], "allow_oa_fulltext": False,
                    }), max_attempts=1,
                )
                session.add(job)
                session.commit()
                return {
                    "execution_id": execution_id, "job_id": job.id,
                    "document_id": document.id, "user_id": user.id,
                    "stored_key": document.stored_path,
                    "fixture_sha256": hashlib.sha256(data).hexdigest(),
                    "fixture_size": len(data),
                }
    import asyncio
    manifest = asyncio.run(seed())
    database.dispose()
    database = build_offline_database(provider_root)
    storage = build_offline_storage(provider_root)
    job_id = int(cast(int | str, manifest["job_id"]))
    if run_once(database, settings=settings, storage=storage) != job_id:
        raise RuntimeError("offline worker did not execute job")
    with database.session() as session:
        row = session.get(Job, job_id)
        if row is None:
            raise RuntimeError("offline workflow terminal status=missing error_type=missing")
        if row.status not in {"partial", "succeeded"}:
            safe_error = (row.error or "unknown workflow error").split(":", 1)[0]
            raise RuntimeError(
                f"offline workflow terminal status={row.status} "
                f"error_type={safe_error}"
            )
        manifest["workflow_status"] = row.status
    if storage.get(str(manifest["stored_key"])) != data:
        raise RuntimeError("offline object content integrity mismatch")
    workspace_resolved = workspace.resolve()
    if workspace_resolved.exists():
        shutil.rmtree(workspace_resolved)
    manifest_path = provider_root / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, separators=(",", ":")))
    database.dispose()
    return 0


def reload_and_cleanup(provider_root: Path, receipt_path: Path) -> int:
    manifest = json.loads((provider_root / MANIFEST_NAME).read_text(encoding="utf-8"))
    database = build_offline_database(provider_root)
    storage = build_offline_storage(provider_root)
    receipt = _receipt(str(manifest["execution_id"]))
    with database.session() as session:
        job = session.get(Job, int(manifest["job_id"]))
        document = session.get(PaperDocument, int(manifest["document_id"]))
        if job is None or document is None or job.status not in {"partial", "succeeded"}:
            raise RuntimeError("fresh process could not reload durable records")
        data = storage.get(document.stored_path)
        digest = hashlib.sha256(data).hexdigest()
        if len(data) != int(manifest["fixture_size"]) or digest != manifest["fixture_sha256"]:
            raise RuntimeError("fresh process content integrity mismatch")
        session.delete(document)
        session.delete(job)
        session.commit()
    storage.delete(str(manifest["stored_key"]))
    if (provider_root / "objects" / str(manifest["stored_key"])).exists():
        raise RuntimeError("offline cleanup did not remove exact object")
    receipt.update({
        "fixture_sha256": manifest["fixture_sha256"], "fixture_size": manifest["fixture_size"],
        "workflow_execution": "PASS", "workflow_terminal_state": "PASS",
        "temp_workspace_removed": "PASS", "fresh_process_reload": "PASS",
        "content_integrity": "PASS", "cleanup": "PASS", "final_status": "PASS",
        "exit_code": 0,
    })
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    database.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "reload"))
    parser.add_argument("--provider-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.phase == "prepare":
        if args.workspace is None:
            raise SystemExit("--workspace is required for prepare")
        return prepare(args.provider_root, args.workspace)
    if args.receipt is None:
        raise SystemExit("--receipt is required for reload")
    return reload_and_cleanup(args.provider_root, args.receipt)


if __name__ == "__main__":
    raise SystemExit(main())
