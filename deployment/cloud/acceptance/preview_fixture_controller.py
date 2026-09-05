"""Fail-closed, local-only cleanup for Preview acceptance fixtures.

This module is intentionally outside the application package.  It operates on
an explicit frozen manifest and an allowlisted SQLAlchemy closure; it never
implements a product deletion endpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import MISSING, asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from research_navigator.models import (
    AgentRun,
    ComparisonRun,
    Favorite,
    GapCandidate,
    GapEvidence,
    GapExplanation,
    IdempotencyRecord,
    Job,
    JobEvent,
    PaperAnalysisRecord,
    PaperChunk,
    PaperDocument,
    PaperSet,
    PaperSetItem,
    PlanItem,
    ResearchPlan,
    ResearchProject,
    SourceRequest,
    ToolCall,
    User,
)


class OwnershipAmbiguous(RuntimeError):
    """Raised when the manifest cannot prove ownership of a row."""


class DatabaseIdentityError(RuntimeError):
    """Raised when the target database is not the approved test database."""


class ExactObjectStore(Protocol):
    def head(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...


class Boto3ExactObjectStore:
    """R2 adapter used only by this local acceptance controller."""

    def __init__(
        self,
        *,
        bucket: str,
        account_id: str,
        access_key: str,
        secret_key: str,
        endpoint: str | None = None,
    ) -> None:
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint or f"https://{account_id}.r2.cloudflarestorage.com",
            region_name="auto",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def head(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


ID_FIELDS = (
    "project_ids",
    "owned_paper_ids",
    "borrowed_paper_ids",
    "favorite_ids",
    "paper_set_ids",
    "paper_set_item_ids",
    "comparison_run_ids",
    "gap_candidate_ids",
    "gap_evidence_ids",
    "gap_explanation_ids",
    "paper_analysis_ids",
    "research_plan_ids",
    "plan_item_ids",
    "job_ids",
    "job_event_ids",
    "source_request_ids",
    "tool_call_ids",
    "agent_run_ids",
    "paper_document_ids",
    "paper_chunk_ids",
    "idempotency_record_ids",
)


@dataclass(slots=True)
class FixtureManifest:
    execution_id: str
    deployed_source_commit: str
    acceptance_tool_commit: str
    preview_host: str
    account_user_id: int
    account_identity_hash: str
    project_ids: list[int] = field(default_factory=list)
    owned_paper_ids: list[int] = field(default_factory=list)
    borrowed_paper_ids: list[int] = field(default_factory=list)
    favorite_ids: list[int] = field(default_factory=list)
    paper_set_ids: list[int] = field(default_factory=list)
    paper_set_item_ids: list[int] = field(default_factory=list)
    comparison_run_ids: list[int] = field(default_factory=list)
    gap_candidate_ids: list[int] = field(default_factory=list)
    gap_evidence_ids: list[int] = field(default_factory=list)
    gap_explanation_ids: list[int] = field(default_factory=list)
    paper_analysis_ids: list[int] = field(default_factory=list)
    research_plan_ids: list[int] = field(default_factory=list)
    plan_item_ids: list[int] = field(default_factory=list)
    job_ids: list[int] = field(default_factory=list)
    job_event_ids: list[int] = field(default_factory=list)
    source_request_ids: list[int] = field(default_factory=list)
    tool_call_ids: list[int] = field(default_factory=list)
    agent_run_ids: list[int] = field(default_factory=list)
    paper_document_ids: list[int] = field(default_factory=list)
    paper_chunk_ids: list[int] = field(default_factory=list)
    idempotency_record_ids: list[int] = field(default_factory=list)
    r2_object_keys: list[str] = field(default_factory=list)
    created_at: str = ""
    last_updated_at: str = ""
    frozen_at: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> FixtureManifest:
        values: dict[str, Any] = {}
        for key, field_info in cls.__dataclass_fields__.items():
            if key in value:
                values[key] = value[key]
            elif field_info.default_factory is not MISSING:
                values[key] = field_info.default_factory()
            elif field_info.default is not MISSING:
                values[key] = field_info.default
            else:
                raise OwnershipAmbiguous(f"manifest is missing required field: {key}")
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_manifest_bytes(manifest: FixtureManifest) -> bytes:
    value = manifest.to_dict()
    value.pop("frozen_at", None)
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def manifest_sha256(manifest: FixtureManifest) -> str:
    return hashlib.sha256(_canonical_manifest_bytes(manifest)).hexdigest()


def write_manifest_atomic(path: Path, manifest: FixtureManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def read_manifest(path: Path) -> FixtureManifest:
    return FixtureManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def validate_manifest(manifest: FixtureManifest) -> None:
    if not manifest.execution_id.startswith("rn223-preview-fixture-"):
        raise OwnershipAmbiguous("execution_id is not an acceptance fixture identity")
    if manifest.account_user_id <= 0:
        raise OwnershipAmbiguous("account_user_id must be a positive existing account root")
    if not manifest.preview_host.startswith("https://"):
        raise OwnershipAmbiguous("preview_host must be an HTTPS origin")
    for field_name in ID_FIELDS:
        values = getattr(manifest, field_name)
        if any(not isinstance(item, int) or item <= 0 for item in values):
            raise OwnershipAmbiguous(f"{field_name} contains an invalid primary key")
    if len(manifest.r2_object_keys) > 20:
        raise OwnershipAmbiguous("R2 blast radius exceeds 20 exact keys")
    for key in manifest.r2_object_keys:
        if (
            not isinstance(key, str)
            or not key
            or key.startswith(("/", "\\"))
            or ".." in key.split("/")
            or "?" in key
            or "#" in key
        ):
            raise OwnershipAmbiguous("R2 object keys must be exact safe relative keys")


def freeze_manifest(manifest: FixtureManifest) -> str:
    validate_manifest(manifest)
    if manifest.frozen_at:
        return manifest_sha256(manifest)
    from datetime import UTC, datetime

    manifest.frozen_at = datetime.now(UTC).isoformat()
    return manifest_sha256(manifest)


def require_manifest_hash(manifest: FixtureManifest, expected: str) -> None:
    if not manifest.frozen_at:
        raise OwnershipAmbiguous("manifest must be frozen before execute")
    if manifest_sha256(manifest) != expected:
        raise OwnershipAmbiguous("manifest SHA-256 mismatch")


def validate_database_identity(*, backend: str, target_database: str) -> None:
    if backend.lower() != "turso":
        raise DatabaseIdentityError("DATABASE_BACKEND must be turso")
    if target_database != "researchnavigator-rn223":
        raise DatabaseIdentityError("target database is not researchnavigator-rn223")
    if target_database == "researchnavigator":
        raise DatabaseIdentityError("old researchnavigator database is forbidden")


def validate_database_host(*, target_database: str, database_url: str) -> None:
    """Require the connection host to identify the approved database."""
    host = (urlsplit(database_url).hostname or "").lower()
    expected = target_database.lower()
    if not host or expected not in host or "researchnavigator" not in host:
        raise DatabaseIdentityError("database host does not identify researchnavigator-rn223")
    if host.startswith("researchnavigator.") or "researchnavigator-rn223" not in host:
        raise DatabaseIdentityError("old or unexpected researchnavigator database host")


def _normalise_database_url(database_url: str) -> str:
    from research_navigator.config import normalize_turso_database_url

    if database_url.strip().lower().startswith("libsql://"):
        return normalize_turso_database_url(database_url)
    return database_url


@dataclass(frozen=True, slots=True)
class RowSpec:
    name: str
    model: type[Any]
    ids_field: str
    user_field: str | None
    parent_fields: tuple[tuple[str, str], ...] = ()


ROW_SPECS = (
    RowSpec(
        "paper_chunks",
        PaperChunk,
        "paper_chunk_ids",
        "user_id",
        (("document_id", "paper_document_ids"),),
    ),
    RowSpec("paper_documents", PaperDocument, "paper_document_ids", "user_id"),
    RowSpec("tool_calls", ToolCall, "tool_call_ids", "user_id"),
    RowSpec("job_events", JobEvent, "job_event_ids", "user_id"),
    RowSpec("source_requests", SourceRequest, "source_request_ids", "user_id"),
    RowSpec("agent_runs", AgentRun, "agent_run_ids", "user_id"),
    RowSpec(
        "gap_evidence",
        GapEvidence,
        "gap_evidence_ids",
        None,
        (("gap_id", "gap_candidate_ids"),),
    ),
    RowSpec(
        "gap_explanations",
        GapExplanation,
        "gap_explanation_ids",
        "user_id",
        (("gap_id", "gap_candidate_ids"),),
    ),
    RowSpec(
        "plan_items",
        PlanItem,
        "plan_item_ids",
        "user_id",
        (("plan_id", "research_plan_ids"),),
    ),
    RowSpec(
        "paper_set_items",
        PaperSetItem,
        "paper_set_item_ids",
        None,
        (("paper_set_id", "paper_set_ids"),),
    ),
    RowSpec("favorites", Favorite, "favorite_ids", "user_id"),
    RowSpec("paper_analyses", PaperAnalysisRecord, "paper_analysis_ids", "user_id"),
    RowSpec("comparison_runs", ComparisonRun, "comparison_run_ids", "user_id"),
    RowSpec("gap_candidates", GapCandidate, "gap_candidate_ids", "user_id"),
    RowSpec("research_plans", ResearchPlan, "research_plan_ids", "user_id"),
    RowSpec("paper_sets", PaperSet, "paper_set_ids", "user_id"),
    RowSpec("jobs", Job, "job_ids", "user_id"),
    RowSpec("research_projects", ResearchProject, "project_ids", "user_id"),
    RowSpec("idempotency_records", IdempotencyRecord, "idempotency_record_ids", "user_id"),
)


def _rows_for_spec(session: Session, spec: RowSpec, manifest: FixtureManifest) -> list[Any]:
    ids = getattr(manifest, spec.ids_field)
    if not ids:
        return []
    rows = list(session.scalars(select(spec.model).where(spec.model.id.in_(ids))))
    allowed = set(ids)
    allowed_papers = set(manifest.owned_paper_ids) | set(manifest.borrowed_paper_ids)
    allowed_projects = set(manifest.project_ids)
    allowed_sets = set(manifest.paper_set_ids)
    allowed_jobs = set(manifest.job_ids)
    allowed_documents = set(manifest.paper_document_ids)
    for row in rows:
        if row.id not in allowed:
            raise OwnershipAmbiguous(f"{spec.name} row escaped manifest IDs")
        if spec.user_field and getattr(row, spec.user_field) != manifest.account_user_id:
            raise OwnershipAmbiguous(f"{spec.name} row has a different owner")
        for field_name, manifest_field in spec.parent_fields:
            parent_id = getattr(row, field_name)
            if parent_id not in set(getattr(manifest, manifest_field)):
                raise OwnershipAmbiguous(f"{spec.name} row references an unowned parent")
        for field_name, allowed_values, label in (
            ("project_id", allowed_projects, "project"),
            ("paper_set_id", allowed_sets, "paper set"),
            ("job_id", allowed_jobs, "job"),
            ("document_id", allowed_documents, "document"),
        ):
            if hasattr(row, field_name):
                parent_id = getattr(row, field_name)
                if parent_id is not None and parent_id not in allowed_values:
                    raise OwnershipAmbiguous(f"{spec.name} row references an unowned {label}")
        if (
            hasattr(row, "paper_id")
            and row.paper_id is not None
            and row.paper_id not in allowed_papers
        ):
            raise OwnershipAmbiguous(f"{spec.name} row references an unowned paper")
        if hasattr(row, "run_id") and row.run_id is not None:
            owner_run = session.scalar(
                select(AgentRun).where(AgentRun.run_id == row.run_id)
            )
            if owner_run is None or owner_run.id not in set(manifest.agent_run_ids):
                raise OwnershipAmbiguous(f"{spec.name} row references an unowned agent run")
    return rows


def collect_cleanup_plan(session: Session, manifest: FixtureManifest) -> dict[str, list[int]]:
    validate_manifest(manifest)
    _validate_account_identity(session, manifest)
    plan: dict[str, list[int]] = {}
    total = 0
    for spec in ROW_SPECS:
        rows = _rows_for_spec(session, spec, manifest)
        ids = sorted(int(row.id) for row in rows)
        if len(ids) > 100:
            raise OwnershipAmbiguous(f"{spec.name} blast radius exceeds 100 rows")
        plan[spec.name] = ids
        total += len(ids)
    if total > 500:
        raise OwnershipAmbiguous("database blast radius exceeds 500 rows")
    return plan


def _delete_plan(session: Session, plan: dict[str, list[int]]) -> None:
    by_name = {spec.name: spec for spec in ROW_SPECS}
    for name, ids in plan.items():
        if ids:
            session.query(by_name[name].model).filter(by_name[name].model.id.in_(ids)).delete(
                synchronize_session=False
            )


def execute_cleanup(
    session_factory: sessionmaker[Session],
    manifest: FixtureManifest,
    expected_sha256: str,
    *,
    object_store: ExactObjectStore | None = None,
) -> dict[str, Any]:
    require_manifest_hash(manifest, expected_sha256)
    with session_factory() as session:
        plan = collect_cleanup_plan(session, manifest)
        _delete_plan(session, plan)
        session.commit()
    if object_store:
        for key in manifest.r2_object_keys:
            if object_store.head(key):
                object_store.delete(key)
    return verify_cleanup(session_factory, manifest, object_store=object_store) | {
        "database_cleanup": "PASS",
        "r2_cleanup": "PASS" if object_store else "NOT_APPLICABLE",
    }


def verify_cleanup(
    session_factory: sessionmaker[Session],
    manifest: FixtureManifest,
    *,
    object_store: ExactObjectStore | None = None,
) -> dict[str, Any]:
    validate_manifest(manifest)
    with session_factory() as session:
        _validate_account_identity(session, manifest)
        remaining = collect_cleanup_plan(session, manifest)
        if any(remaining.values()):
            raise OwnershipAmbiguous(f"fixture rows remain: {remaining}")
        if session.get(User, manifest.account_user_id) is None:
            raise OwnershipAmbiguous("account root was deleted")
    if object_store and any(object_store.head(key) for key in manifest.r2_object_keys):
        raise OwnershipAmbiguous("fixture R2 object remains")
    return {"database_rows_after": 0, "r2_objects_after": 0 if object_store else None}


def _validate_account_identity(session: Session, manifest: FixtureManifest) -> None:
    """Prove the manifest still names the intended account root."""
    account = session.get(User, manifest.account_user_id)
    if account is None:
        raise OwnershipAmbiguous("account root is missing")
    actual_hash = hashlib.sha256(account.email.encode("utf-8")).hexdigest()
    if actual_hash != manifest.account_identity_hash:
        raise OwnershipAmbiguous("manifest account identity does not match database")


def audit() -> dict[str, Any]:
    return {
        "default_mode": "dry-run",
        "database_identity": "target database must be researchnavigator-rn223",
        "account_root": "never delete",
        "borrowed_papers": "never delete",
        "r2": "exact HEAD/DELETE/absence only",
        "row_specs": [spec.name for spec in ROW_SPECS],
    }


def _build_object_store(manifest: FixtureManifest) -> Boto3ExactObjectStore | None:
    if not manifest.r2_object_keys:
        return None
    def required_env(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise OwnershipAmbiguous(f"{name} is required for a manifest with object keys")
        return value

    return Boto3ExactObjectStore(
        bucket=required_env("R2_BUCKET"),
        account_id=required_env("R2_ACCOUNT_ID"),
        access_key=required_env("R2_ACCESS_KEY_ID"),
        secret_key=required_env("R2_SECRET_ACCESS_KEY"),
        endpoint=os.getenv("R2_ENDPOINT"),
    )


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("audit", "dry-run", "execute", "verify"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--database-url", default=os.getenv("TURSO_DATABASE_URL"))
    parser.add_argument("--backend", default=os.getenv("DATABASE_BACKEND"))
    parser.add_argument("--target-database", default=os.getenv("RN223_TARGET_DATABASE"))
    args = parser.parse_args()
    if args.mode == "audit":
        print(json.dumps(audit(), sort_keys=True))
        return 0
    if not args.manifest:
        parser.error("--manifest is required")
    manifest = read_manifest(args.manifest)
    if args.mode == "dry-run":
        if (
            not args.database_url
            or args.backend != "turso"
            or args.target_database != "researchnavigator-rn223"
        ):
            raise DatabaseIdentityError("dry-run requires the approved Turso target identity")
        validate_database_identity(backend=args.backend, target_database=args.target_database)
        validate_database_host(target_database=args.target_database, database_url=args.database_url)
    if not args.database_url or not args.backend or not args.target_database:
        parser.error("database URL, backend, and target database are required for this mode")
    validate_database_identity(backend=args.backend, target_database=args.target_database)
    validate_database_host(target_database=args.target_database, database_url=args.database_url)
    from research_navigator.db import Database

    database = Database.from_url(_normalise_database_url(args.database_url))
    if database.backend_name != "turso":
        raise DatabaseIdentityError("resolved database dialect is not turso")
    if args.mode == "dry-run":
        with database.session_factory() as session:
            plan = collect_cleanup_plan(session, manifest)
        print(
            json.dumps(
                {"mode": "dry-run", "manifest_sha256": manifest_sha256(manifest), "plan": plan},
                sort_keys=True,
            )
        )
        return 0
    if args.mode == "execute":
        if not args.manifest_sha256:
            parser.error("--manifest-sha256 is required for execute")
        object_store = _build_object_store(manifest)
        result = execute_cleanup(
            database.session_factory,
            manifest,
            args.manifest_sha256,
            object_store=object_store,
        )
    else:
        result = verify_cleanup(
            database.session_factory,
            manifest,
            object_store=_build_object_store(manifest),
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
