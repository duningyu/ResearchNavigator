from __future__ import annotations

import pytest
from deployment.cloud.parity import run_turso_schema_bootstrap as bootstrap


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
