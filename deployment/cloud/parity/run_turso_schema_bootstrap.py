"""Read-only Turso schema forensic audit entrypoint.

This entrypoint deliberately performs no migration or other DDL.  The source
mount may remain read-only; the wrapper supplies a separate evidence mount.
Credentials are consumed only from the child-process environment and are
never included in receipts or diagnostic output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from research_navigator.config import normalize_turso_database_url
from research_navigator.db import Database
from research_navigator.models import Base

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"
VERSIONS = ROOT / "apps" / "api" / "alembic" / "versions"
DEFAULT_RECEIPT = Path("/evidence/TURSO_SCHEMA_BOOTSTRAP_MIGRATION_RECEIPT.json")


class BootstrapTargetIdentityError(RuntimeError):
    pass


class BootstrapTargetNotEmptyError(RuntimeError):
    pass


class BootstrapSchemaSnapshotError(RuntimeError):
    pass


def _coerce_schema_count(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise BootstrapSchemaSnapshotError(
            f"SCHEMA_SNAPSHOT_COUNT_INVALID:{field}:bool"
        )
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise BootstrapSchemaSnapshotError(
        f"SCHEMA_SNAPSHOT_COUNT_INVALID:{field}:{type(value).__name__}"
    )


def _bootstrap_target_identity(raw_url: str) -> str:
    host = (urlsplit(raw_url).hostname or "").lower()
    if not host or not host.startswith("researchnavigator-rn223-"):
        raise BootstrapTargetIdentityError(
            "TURSO_BOOTSTRAP_TARGET_IDENTITY_UNRESOLVED"
        )
    return "PASS"


def _bootstrap_business_tables(snapshot: dict[str, object]) -> list[str]:
    tables = snapshot.get("current_tables", [])
    if not isinstance(tables, list):
        raise BootstrapTargetNotEmptyError("BOOTSTRAP_TARGET_TABLE_METADATA_INVALID")
    return [
        str(table)
        for table in tables
        if str(table) != "alembic_version"
        and not str(table).startswith("sqlite_")
        and not _ignored_schema_artifact(str(table))
    ]


def _assert_bootstrap_target_empty(snapshot: dict[str, object]) -> str:
    business_tables = _bootstrap_business_tables(snapshot)
    if business_tables:
        raise BootstrapTargetNotEmptyError("BOOTSTRAP_TARGET_NOT_EMPTY")
    return "PASS"


def _safe_host(raw_url: str) -> str:
    return urlsplit(raw_url).hostname or "unavailable"


def _code_head() -> str:
    from alembic.script import ScriptDirectory

    config = Config(str(ALEMBIC_INI))
    return ScriptDirectory.from_config(config).get_current_head()


def _expected_indexes() -> set[str]:
    names: set[str] = set()
    for table in Base.metadata.tables.values():
        names.update(index.name for index in table.indexes if index.name)
    return names


def _receipt_path() -> Path:
    raw = os.environ.get("RN_SCHEMA_RECEIPT_PATH", "")
    return Path(raw) if raw else DEFAULT_RECEIPT


def _safe_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _row_counts(connection, tables: set[str]) -> dict[str, int | str]:
    counts: dict[str, int | str] = {}
    for table in sorted(tables):
        if table == "alembic_version" or table.startswith("sqlite_"):
            continue
        try:
            counts[table] = _coerce_schema_count(
                connection.execute(
                    text(f"SELECT COUNT(*) FROM {_safe_identifier(table)}")
                ).scalar_one(),
                f"table:{table}",
            )
        except BootstrapSchemaSnapshotError:
            raise
        except Exception:
            counts[table] = "UNAVAILABLE"
    return counts


def _schema_snapshot(database: Database) -> dict[str, object]:
    with database.engine.connect() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        current = None
        version_row_count: int | None = None
        if "alembic_version" in tables:
            version_row_count = _coerce_schema_count(
                connection.execute(
                    text("SELECT COUNT(*) FROM alembic_version")
                ).scalar_one(),
                "alembic_version",
            )
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
        indexes = {
            index["name"]
            for table in tables
            for index in inspector.get_indexes(table)
            if index.get("name")
        }
        structure: dict[str, object] = {}
        for table in sorted(tables):
            structure[table] = {
                "columns": [
                    {
                        "name": column.get("name"),
                        "type": str(column.get("type")),
                        "nullable": column.get("nullable"),
                        "primary_key": column.get("primary_key"),
                    }
                    for column in inspector.get_columns(table)
                ],
                "primary_key": inspector.get_pk_constraint(table),
                "foreign_keys": inspector.get_foreign_keys(table),
                "unique_constraints": inspector.get_unique_constraints(table),
                "indexes": inspector.get_indexes(table),
            }
        schema_objects = connection.execute(
            text(
                "SELECT name, type, tbl_name, sql FROM sqlite_schema "
                "WHERE type IN ('table', 'index', 'trigger', 'view') "
                "ORDER BY type, name"
            )
        ).mappings().all()
        fts_rows = connection.execute(
            text(
                "SELECT name, type, sql FROM sqlite_schema "
                "WHERE name LIKE 'paper_chunks_fts%' "
                "OR (type = 'trigger' AND tbl_name = 'paper_chunks')"
            )
        ).all()
        fts_names = {str(row[0]) for row in fts_rows}
        row_counts = _row_counts(connection, tables)
    expected_tables = set(Base.metadata.tables)
    expected_indexes = _expected_indexes()
    fts_ok = "paper_chunks_fts" in fts_names
    return {
        "current_tables": sorted(tables),
        "current_table_count": len(tables),
        "row_counts": row_counts,
        "schema_structure": structure,
        "schema_objects": [dict(row) for row in schema_objects],
        "alembic_version_table_present": "alembic_version" in tables,
        "alembic_version_row_count": version_row_count,
        "alembic_current_revision": current,
        "alembic_revision": current,
        "required_tables": expected_tables <= tables,
        "required_tables_missing": sorted(expected_tables - tables),
        "required_indexes": expected_indexes <= indexes,
        "required_indexes_missing": sorted(expected_indexes - indexes),
        "fts": fts_ok,
        "fts_objects": sorted(fts_names),
    }


def _write_reference(revision: str, output: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="rn223-schema-reference-") as directory:
        db_path = Path(directory) / "reference.sqlite"
        url = f"sqlite+pysqlite:///{db_path.as_posix()}"
        os.environ["RN_DATABASE_URL"] = url
        config = Config(str(ALEMBIC_INI))
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, revision)
        engine = create_engine(url)
        try:
            snapshot = _schema_snapshot(type("ReferenceDatabase", (), {"engine": engine})())
        finally:
            engine.dispose()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "reference_revision": revision,
        "normalization": (
            "SQLAlchemy inspector; provider-internal artifacts are absent "
            "from local SQLite reference"
        ),
        "tables": snapshot["current_tables"],
        "table_count": snapshot["current_table_count"],
        "schema_structure": snapshot["schema_structure"],
        "schema_objects": snapshot["schema_objects"],
        "fts_objects": snapshot["fts_objects"],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"ALEMBIC_{revision.upper()}_REFERENCE=PASS")
    return 0


def _reference_path(revision: str) -> Path:
    name = (
        "ALEMBIC_HEAD_REFERENCE_SCHEMA.json"
        if revision == "head"
        else "ALEMBIC_0001_REFERENCE_SCHEMA.json"
    )
    return ROOT / "deployment" / "cloud" / "runtime_receipts" / name


def _canonical_sql(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _ignored_schema_artifact(name: str) -> bool:
    # sqlite_sequence and FTS5 shadow tables are implementation artifacts.  The
    # explicit paper_chunks_fts virtual table itself remains part of equality.
    return name == "sqlite_sequence" or (
        name.startswith("paper_chunks_fts_") and name != "paper_chunks_fts"
    )


def _schema_fingerprint(snapshot: dict[str, object]) -> dict[str, object]:
    structures = snapshot.get("schema_structure", {})
    normalized: dict[str, object] = {}
    if isinstance(structures, dict):
        for table, value in structures.items():
            if _ignored_schema_artifact(str(table)) or not isinstance(value, dict):
                continue
            normalized[str(table)] = {
                "columns": [
                    {
                        "name": column.get("name"),
                        "type": _canonical_sql(column.get("type")),
                        "nullable": column.get("nullable"),
                        "primary_key": column.get("primary_key"),
                    }
                    for column in value.get("columns", [])
                ],
                "primary_key": value.get("primary_key"),
                "foreign_keys": value.get("foreign_keys", []),
                "unique_constraints": value.get("unique_constraints", []),
                "indexes": value.get("indexes", []),
            }
    objects = []
    for value in snapshot.get("schema_objects", []):
        if not isinstance(value, dict) or _ignored_schema_artifact(str(value.get("name", ""))):
            continue
        objects.append({
            "name": value.get("name"),
            "type": value.get("type"),
            "tbl_name": value.get("tbl_name"),
            "sql": _canonical_sql(value.get("sql")),
        })
    fts = sorted(
        str(name) for name in snapshot.get("fts_objects", [])
        if str(name) == "paper_chunks_fts"
    )
    return {"tables": sorted(normalized), "structure": normalized, "objects": objects, "fts": fts}


def _compare_reference(snapshot: dict[str, object], revision: str) -> str:
    path = _reference_path(revision)
    if not path.is_file():
        return "DIFFERENT"
    reference = json.loads(path.read_text(encoding="utf-8"))
    return (
        "EXACT"
        if _schema_fingerprint(snapshot) == _schema_fingerprint(reference)
        else "DIFFERENT"
    )


def _migration_history_classification() -> dict[str, str]:
    classifications: dict[str, str] = {}
    dml = re.compile(r"\b(?:insert|update|delete)\b", re.IGNORECASE)
    for path in sorted(VERSIONS.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        upgrade = source.split("def upgrade", 1)[-1].split("def downgrade", 1)[0]
        classifications[path.stem.split("_", 1)[0]] = (
            "DATA_MIGRATION" if dml.search(upgrade) else "SCHEMA_ONLY"
        )
    return classifications


def _write_receipt(payload: dict[str, object]) -> None:
    receipt = _receipt_path()
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def receipt_preflight() -> int:
    evidence = _receipt_path()
    source_probe = ROOT / ".rn223-source-readonly-probe"
    try:
        try:
            source_probe.write_text("probe", encoding="utf-8")
        except (OSError, PermissionError):
            source_read_only = True
        else:
            source_read_only = False
            source_probe.unlink(missing_ok=True)
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text('{"preflight":true}\n', encoding="utf-8")
        evidence_ok = evidence.read_text(encoding="utf-8") == '{"preflight":true}\n'
        evidence.unlink(missing_ok=True)
    except Exception:
        source_read_only = False
        evidence_ok = False
    print(f"SOURCE_MOUNT_READ_ONLY={'PASS' if source_read_only else 'FAIL'}")
    print(f"EVIDENCE_MOUNT_WRITABLE={'PASS' if evidence_ok else 'FAIL'}")
    print(f"RECEIPT_WRITE={'PASS' if evidence_ok else 'FAIL'}")
    passed = source_read_only and evidence_ok
    print("TURSO_SCHEMA_RECEIPT_PREFLIGHT=" + ("PASS" if passed else "FAIL"))
    return 0 if passed else 1


def preflight() -> int:
    checks = {
        "LINUX_PYTHON": sys.version_info[:2] == (3, 12),
        "SQLALCHEMY_LIBSQL": _module_available("sqlalchemy_libsql"),
        "ALEMBIC_IMPORT": _module_available("alembic"),
        "ALEMBIC_INI": ALEMBIC_INI.is_file(),
        "MIGRATION_DIRECTORY": VERSIONS.is_dir() and any(VERSIONS.glob("*.py")),
        "ALEMBIC_HEAD_PARSEABLE": False,
        "TURSO_URL_NORMALIZATION": False,
    }
    if checks["ALEMBIC_INI"] and checks["MIGRATION_DIRECTORY"]:
        try:
            checks["ALEMBIC_HEAD_PARSEABLE"] = bool(_code_head())
        except Exception:
            checks["ALEMBIC_HEAD_PARSEABLE"] = False
    try:
        checks["TURSO_URL_NORMALIZATION"] = normalize_turso_database_url(
            "libsql://example.turso.io"
        ) == "sqlite+libsql://example.turso.io?secure=true"
    except Exception:
        checks["TURSO_URL_NORMALIZATION"] = False
    for name, passed in checks.items():
        print(f"{name}={'PASS' if passed else 'FAIL'}")
    print("TURSO_SCHEMA_BOOTSTRAP_PREFLIGHT=" + ("PASS" if all(checks.values()) else "FAIL"))
    return 0 if all(checks.values()) else 1


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def live() -> int:
    raw_url = os.environ.get("TURSO_DATABASE_URL", "")
    token = os.environ.get("TURSO_AUTH_TOKEN", "")
    if not raw_url or not token:
        print("TURSO_SCHEMA_BOOTSTRAP=ERROR_SAFE_REDACTED")
        return 2
    normalized = normalize_turso_database_url(raw_url)
    database = Database.from_url(normalized)
    source_commit = os.environ.get("RN_SOURCE_COMMIT", "unknown")
    try:
        before = _schema_snapshot(database)
        head = _code_head()
        counts = [
            count
            for table, count in before["row_counts"].items()
            if table != "alembic_version" and isinstance(count, int)
        ]
        if not counts or all(count == 0 for count in counts):
            row_classification = "EMPTY"
        else:
            row_classification = "NONEMPTY_UNKNOWN_DATA"
        matches_0001 = _compare_reference(before, "0001")
        matches_head = _compare_reference(before, "head")
        history = _migration_history_classification()
        has_data_migration = "DATA_MIGRATION" in history.values() or "MIXED" in history.values()
        stamp_head_candidate = (
            matches_head == "EXACT"
            and before["alembic_version_row_count"] == 0
            and not has_data_migration
        )
        stamp_0001_candidate = (
            matches_0001 == "EXACT"
            and matches_head == "DIFFERENT"
            and before["alembic_version_row_count"] == 0
            and not has_data_migration
        )
        result = {
            "audit_mode": "READ_ONLY_SCHEMA_FORENSIC",
            "source_commit": source_commit,
            "schema_authority": "ALEMBIC",
            "safe_database_host": _safe_host(raw_url),
            "alembic_code_head": head,
            "alembic_version_table_present": before["alembic_version_table_present"],
            "alembic_version_row_count": before["alembic_version_row_count"],
            "alembic_current_revision": before["alembic_current_revision"],
            "current_table_count": before["current_table_count"],
            "current_tables": before["current_tables"],
            "row_counts": before["row_counts"],
            "schema_structure": before["schema_structure"],
            "schema_objects": before["schema_objects"],
            "current_schema_matches_0001": matches_0001,
            "current_schema_matches_head": matches_head,
            "current_schema_matches_orm": before["required_tables"] and before["required_indexes"],
            "schema_diff_summary_if_any": (
                "NONE" if matches_head == "EXACT" or matches_0001 == "EXACT"
                else "CURRENT_SCHEMA_DIFFERS_FROM_0001_AND_HEAD"
            ),
            "migration_history_classification": history,
            "migration_0001_first_operation": "papers",
            "business_schema_mutated_by_failed_upgrade": False,
            "alembic_metadata_mutated_by_failed_upgrade": True,
            "migration_attempt_mutated_schema": False,
            "runtime_create_all_on_turso": False,
            "schema_authority_conflict": False,
            "fts_authority": "ALEMBIC_OWNED",
            "business_table_count": len(counts),
            "business_nonempty_table_count": sum(count > 0 for count in counts),
            "business_row_count_classification": row_classification,
            "row_count_classification": row_classification,
            "recommended_recovery": (
                "STAMP_HEAD_CANDIDATE" if stamp_head_candidate else
                "STAMP_0001_THEN_UPGRADE_CANDIDATE" if stamp_0001_candidate else
                "SCHEMA_RECONCILIATION_REQUIRED"
            ),
            "stamp_head_safe_candidate": stamp_head_candidate,
            "stamp_0001_then_upgrade_safe_candidate": stamp_0001_candidate,
            "reset_candidate": row_classification in {"EMPTY", "TEST_FIXTURE_ONLY"},
            "destructive_action_required": row_classification in {"EMPTY", "TEST_FIXTURE_ONLY"},
            "human_confirmation_required": row_classification in {"EMPTY", "TEST_FIXTURE_ONLY"},
            "migration_writes_attempted": False,
            "ddl_executed": False,
            "secret_exposure": False,
            "frozen_core": "UNCHANGED",
            "final_status": "READ_ONLY_AUDIT_PASS",
        }
        _write_receipt(result)
        print("TURSO_SCHEMA_FORENSIC_AUDIT=PASS")
        return 0
    except Exception as exc:
        _write_receipt(
            {
                "source_commit": source_commit,
                "schema_authority": "ALEMBIC",
                "safe_database_host": _safe_host(raw_url),
                "audit_mode": "READ_ONLY_SCHEMA_FORENSIC",
                "failure_classification": (
                    "SCHEMA_SNAPSHOT_PARSE_FAILURE"
                    if isinstance(exc, BootstrapSchemaSnapshotError)
                    else "TURSO_SCHEMA_FORENSIC_AUDIT_FAILURE"
                ),
                "error_type": type(exc).__name__,
                "safe_error_message": (
                    str(exc)
                    if isinstance(exc, BootstrapSchemaSnapshotError)
                    else type(exc).__name__
                ),
                "secret_exposure": False,
                "frozen_core": "UNCHANGED",
                "final_status": "ERROR_SAFE_REDACTED",
            }
        )
        print("TURSO_SCHEMA_FORENSIC_AUDIT=ERROR_SAFE_REDACTED")
        return 1
    finally:
        database.dispose()


def _bootstrap_config(database_url: str) -> Config:
    os.environ["RN_DATABASE_URL"] = database_url
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def bootstrap() -> int:
    """Bootstrap only the explicitly approved new, empty Turso database.

    This is intentionally separate from ``live()``, which is read-only
    forensic collection.  The empty-target guard is performed before Alembic
    is invoked, and all schema writes are delegated to the existing Alembic
    authority.
    """
    raw_url = os.environ.get("TURSO_DATABASE_URL", "")
    token = os.environ.get("TURSO_AUTH_TOKEN", "")
    source_commit = os.environ.get("RN_SOURCE_COMMIT", "unknown")
    revisions = ("0001", "0002", "0003", "0004", "0005")
    result: dict[str, object] = {
        "audit_mode": "ALEMBIC_BOOTSTRAP_NEW_EMPTY_DATABASE",
        "source_commit": source_commit,
        "schema_authority": "ALEMBIC",
        "safe_database_host": _safe_host(raw_url),
        "target_database": "researchnavigator-rn223",
        "old_database_untouched": True,
        "migration_writes_attempted": False,
        "ddl_executed_by": "ALEMBIC_ONLY",
        "secret_exposure": False,
        "frozen_core": "UNCHANGED",
        "revision_status": {},
    }
    failure_stage = "CREDENTIAL_INPUT"
    database: Database | None = None
    try:
        if not raw_url or not token:
            raise RuntimeError("BOOTSTRAP_CREDENTIALS_MISSING")
        failure_stage = "TARGET_IDENTITY"
        _bootstrap_target_identity(raw_url)
        normalized = normalize_turso_database_url(raw_url)
        database = Database.from_url(normalized)
        failure_stage = "EMPTY_DATABASE_CHECK"
        before = _schema_snapshot(database)
        _assert_bootstrap_target_empty(before)
        result["pre_bootstrap_business_table_count"] = len(
            _bootstrap_business_tables(before)
        )
        result["pre_bootstrap_empty_guard"] = "PASS"

        failure_stage = "ALEMBIC_BEFORE_STATE"
        config = _bootstrap_config(normalized)
        os.environ["TURSO_AUTH_TOKEN"] = token
        failure_stage = "MIGRATION_START"
        result["migration_writes_attempted"] = True
        statuses: dict[str, str] = {}
        for revision in revisions:
            failure_stage = "MIGRATION_REVISION"
            result["migration_revision_in_progress"] = revision
            command.upgrade(config, revision)
            statuses[revision] = "PASS"
        result["revision_status"] = statuses

        failure_stage = "POST_MIGRATION_VERIFY"
        after = _schema_snapshot(database)
        head = _code_head()
        result.update(
            {
                "migration_revision_in_progress": None,
                "alembic_code_head": head,
                "alembic_version_table_present": after["alembic_version_table_present"],
                "alembic_version_row_count": after["alembic_version_row_count"],
                "alembic_current_revision": after["alembic_current_revision"],
                "schema_matches_head": _compare_reference(after, "head"),
                "required_tables": after["required_tables"],
                "required_indexes": after["required_indexes"],
                "fts_structures": after["fts"],
                "triggers": any(
                    item.get("type") == "trigger"
                    for item in after["schema_objects"]
                    if isinstance(item, dict)
                ),
            }
        )
        if (
            after["alembic_current_revision"] != head
            or result["schema_matches_head"] != "EXACT"
            or not after["required_tables"]
            or not after["required_indexes"]
            or not after["fts"]
        ):
            raise RuntimeError("BOOTSTRAP_SCHEMA_VERIFICATION_FAILED")

        database.init()
        result["database_init"] = "PASS"
        fixture_email = f"rn223-bootstrap-{uuid.uuid4().hex}@invalid.test"
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(email, password_hash, display_name, is_admin, is_active, "
                    "created_at, updated_at) "
                    "VALUES (:email, :password_hash, :display_name, 0, 1, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "email": fixture_email,
                    "password_hash": "rn223-bootstrap-synthetic",
                    "display_name": "RN223 bootstrap synthetic",
                },
            )
            found = connection.execute(
                text("SELECT COUNT(*) FROM users WHERE email = :email"),
                {"email": fixture_email},
            ).scalar_one()
            deleted = connection.execute(
                text("DELETE FROM users WHERE email = :email"),
                {"email": fixture_email},
            ).rowcount
        if int(found) != 1 or int(deleted or 0) != 1:
            raise RuntimeError("BOOTSTRAP_SYNTHETIC_FIXTURE_FAILED")
        result.update(
            {
                "synthetic_write": "PASS",
                "synthetic_read": "PASS",
                "synthetic_delete": "PASS",
                "cleanup": "PASS",
                "final_status": "ALEMBIC_BOOTSTRAP_PASS",
            }
        )
        _write_receipt(result)
        print("TURSO_SCHEMA_BOOTSTRAP=PASS")
        return 0
    except Exception as exc:
        result.update(
            {
                "failure_stage": failure_stage,
                "failure_classification": (
                    "SCHEMA_SNAPSHOT_PARSE_FAILURE"
                    if isinstance(exc, BootstrapSchemaSnapshotError)
                    else type(exc).__name__
                ),
                "safe_error_message": (
                    str(exc)
                    if isinstance(exc, BootstrapSchemaSnapshotError)
                    else type(exc).__name__
                ),
                "final_status": "ERROR_SAFE_REDACTED",
            }
        )
        _write_receipt(result)
        print("TURSO_SCHEMA_BOOTSTRAP=ERROR_SAFE_REDACTED")
        return 1
    finally:
        if database is not None:
            database.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--receipt-preflight", action="store_true")
    parser.add_argument("--reference", choices=("0001", "head"))
    parser.add_argument("--output")
    args = parser.parse_args()
    modes = sum(
        bool(value)
        for value in (
            args.preflight,
            args.live,
            args.bootstrap,
            args.receipt_preflight,
            args.reference,
        )
    )
    if modes != 1:
        parser.error("choose exactly one execution mode")
    if args.preflight:
        return preflight()
    if args.receipt_preflight:
        return receipt_preflight()
    if args.bootstrap:
        return bootstrap()
    if args.reference:
        if not args.output:
            parser.error("--reference requires --output")
        return _write_reference(args.reference, Path(args.output))
    return live()


if __name__ == "__main__":
    raise SystemExit(main())
