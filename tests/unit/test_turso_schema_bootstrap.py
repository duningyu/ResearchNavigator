from __future__ import annotations

import pytest
from deployment.cloud.parity import run_turso_schema_bootstrap as bootstrap


class _FakeResult:
    def __init__(self, scalar=None) -> None:
        self._scalar = scalar

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return None

    def mappings(self):
        return self

    def all(self):
        return []


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, *_args, **_kwargs):
        if "COUNT(*) FROM alembic_version" in str(statement):
            return _FakeResult("not-a-count")
        return _FakeResult()


class _FakeEngine:
    def connect(self):
        return _FakeConnection()


class _FakeInspector:
    def get_table_names(self):
        return ["alembic_version"]

    def get_indexes(self, _table):
        return []

    def get_columns(self, _table):
        return []

    def get_pk_constraint(self, _table):
        return {}

    def get_foreign_keys(self, _table):
        return []

    def get_unique_constraints(self, _table):
        return []


class _FakeDatabase:
    engine = _FakeEngine()


def test_schema_snapshot_rejects_invalid_count_with_explicit_error(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap, "inspect", lambda _connection: _FakeInspector())
    with pytest.raises(bootstrap.BootstrapSchemaSnapshotError, match="COUNT"):
        bootstrap._schema_snapshot(_FakeDatabase())


@pytest.mark.parametrize("value", [0, "0", 12, "12"])
def test_schema_count_accepts_integer_and_numeric_string(value) -> None:
    assert bootstrap._coerce_schema_count(value, "synthetic") >= 0


@pytest.mark.parametrize("value", [None, "", "not-a-count", True])
def test_schema_count_rejects_invalid_metadata_explicitly(value) -> None:
    with pytest.raises(bootstrap.BootstrapSchemaSnapshotError, match="COUNT"):
        bootstrap._coerce_schema_count(value, "synthetic")


@pytest.mark.parametrize("table", ["sqlite_sequence", "alembic_version", "paper_chunks_fts_data"])
def test_empty_guard_ignores_non_business_schema_objects(table) -> None:
    assert bootstrap._assert_bootstrap_target_empty({"current_tables": [table]}) == "PASS"


@pytest.mark.parametrize("table", ["papers", "users"])
def test_empty_guard_rejects_business_tables(table) -> None:
    with pytest.raises(bootstrap.BootstrapTargetNotEmptyError):
        bootstrap._assert_bootstrap_target_empty({"current_tables": [table]})


def test_bootstrap_accepts_only_new_rn223_database() -> None:
    assert bootstrap._bootstrap_target_identity(
        "libsql://researchnavigator-rn223-duningyu.aws-us-east-1.turso.io"
    ) == "PASS"


def test_bootstrap_rejects_old_database_identity() -> None:
    with pytest.raises(bootstrap.BootstrapTargetIdentityError):
        bootstrap._bootstrap_target_identity(
            "libsql://researchnavigator-duningyu.aws-us-east-1.turso.io"
        )


def test_bootstrap_rejects_any_existing_business_table() -> None:
    snapshot = {"current_tables": ["alembic_version", "papers"]}
    with pytest.raises(bootstrap.BootstrapTargetNotEmptyError):
        bootstrap._assert_bootstrap_target_empty(snapshot)


def test_bootstrap_allows_empty_target_with_empty_version_table() -> None:
    snapshot = {"current_tables": ["alembic_version"]}
    assert bootstrap._assert_bootstrap_target_empty(snapshot) == "PASS"


def test_schema_fingerprint_ignores_foreign_key_order() -> None:
    base = {
        "columns": [],
        "primary_key": {},
        "foreign_keys": [
            {"referred_table": "users", "constrained_columns": ["user_id"]},
            {"referred_table": "projects", "constrained_columns": ["project_id"]},
        ],
        "unique_constraints": [],
        "indexes": [],
    }
    reversed_structure = dict(base)
    reversed_structure["foreign_keys"] = list(reversed(base["foreign_keys"]))
    left = {"schema_structure": {"jobs": base}, "schema_objects": [], "fts_objects": []}
    right = {
        "schema_structure": {"jobs": reversed_structure},
        "schema_objects": [],
        "fts_objects": [],
    }
    assert bootstrap._schema_fingerprint(left) == bootstrap._schema_fingerprint(right)


def test_required_indexes_follow_migration_reference(monkeypatch) -> None:
    monkeypatch.setattr(
        bootstrap,
        "_reference_index_names",
        lambda: {"ix_migration_index"},
        raising=False,
    )
    assert bootstrap._expected_indexes() == {"ix_migration_index"}


def test_schema_diff_summary_is_identifier_only(monkeypatch, tmp_path) -> None:
    reference_path = tmp_path / "head.json"
    empty_structure = {
        "columns": [],
        "primary_key": {},
        "foreign_keys": [],
        "unique_constraints": [],
        "indexes": [],
    }
    reference = {
        "schema_structure": {"papers": empty_structure, "users": empty_structure},
        "schema_objects": [
            {"name": "ix_users_email", "type": "index", "tbl_name": "users"}
        ],
        "fts_objects": ["paper_chunks_fts"],
    }
    snapshot = {
        "schema_structure": {"papers": empty_structure, "jobs": empty_structure},
        "schema_objects": [
            {"name": "ix_jobs_status", "type": "index", "tbl_name": "jobs"}
        ],
        "fts_objects": [],
    }
    monkeypatch.setattr(bootstrap, "_reference_path", lambda _revision: reference_path)
    reference_path.write_text(__import__("json").dumps(reference), encoding="utf-8")
    summary = bootstrap._schema_diff_summary(snapshot, "head")
    assert summary["missing_tables"] == ["users"]
    assert summary["extra_tables"] == ["jobs"]
    assert summary["missing_objects"] == [("index", "ix_users_email")]
    assert summary["extra_objects"] == [("index", "ix_jobs_status")]
    assert summary["fts_match"] is False
