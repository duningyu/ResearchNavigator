"""Live smoke tests for the E4.17 shared, test-only fixture loader."""

from pathlib import Path

import pytest

from tests.support.e4_17_shared_fixture_loader import (
    LoaderIsolationError,
    SharedFixtureLoader,
)


CAPABILITIES = (
    "cap_ux011",
    "cap_ux028",
    "cap_ux029",
    "cap_ux030",
    "cap_ux048",
    "cap_ux055",
    "cap_ux056",
    "cap_ux058",
)


@pytest.mark.parametrize("capability_id", CAPABILITIES)
def test_e4_17_capability_is_live_and_isolated(tmp_path: Path, capability_id: str) -> None:
    state = SharedFixtureLoader(tmp_path).load(capability_id)

    assert state.test_only is True
    assert state.scientific_claim_allowed is False
    assert state.live_smoke is True
    assert state.cleanup_verified is True
    assert state.db_path.startswith(str(tmp_path))
    assert state.observed["paper_count"] >= 1


def test_e4_17_profile_change_invalidates_recommendation(tmp_path: Path) -> None:
    state = SharedFixtureLoader(tmp_path).load("cap_ux011")

    assert state.observed["after_profile_change"]["is_current"] is False


def test_e4_17_metadata_only_fixture_is_read_back_from_product(tmp_path: Path) -> None:
    state = SharedFixtureLoader(tmp_path).load("cap_ux030")

    assert state.observed["content_evidence_level"] == "metadata_only"


def test_e4_17_loader_fails_closed_for_non_sqlite(tmp_path: Path) -> None:
    with pytest.raises(LoaderIsolationError):
        SharedFixtureLoader(tmp_path, database_backend="turso").load("cap_ux030")
