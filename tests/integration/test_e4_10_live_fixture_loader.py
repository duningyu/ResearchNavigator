from pathlib import Path

import pytest

from tests.support.e4_10_live_fixture_loader import (
    LiveFixtureLoader,
    LoaderIsolationError,
)


def test_live_loader_materializes_empty_search_through_real_app(tmp_path: Path) -> None:
    state = LiveFixtureLoader(tmp_path).load("cap_ux025")

    assert state.capability_id == "cap_ux025"
    assert state.live_smoke is True
    assert state.test_only is True
    assert state.scientific_claim_allowed is False
    assert state.observed_result_count == 0


def test_live_loader_materializes_long_search_session_through_real_app(tmp_path: Path) -> None:
    state = LiveFixtureLoader(tmp_path).load("cap_ux001")

    assert state.live_smoke is True
    assert state.session_id is not None
    assert state.observed_result_count == 60
    assert state.entity_ids["paper_count"] == 60


def test_live_loader_materializes_refreshable_search_session_through_real_app(tmp_path: Path) -> None:
    state = LiveFixtureLoader(tmp_path).load("cap_ux002")

    assert state.live_smoke is True
    assert state.state_owner == "BROWSER_SESSION"
    assert state.session_id is not None
    assert state.entity_ids["paper_count"] == 60
    assert state.production_path_touched.startswith("real FastAPI routes")
    assert state.cleanup_verified is True


def test_live_loader_materializes_cross_account_isolation(tmp_path: Path) -> None:
    state = LiveFixtureLoader(tmp_path).load("cap_ux078")

    assert state.live_smoke is True
    assert state.entity_ids["account_count"] == 2
    assert state.entity_ids["forbidden_status"] == 404


def test_live_loader_fails_closed_for_non_isolated_database(tmp_path: Path) -> None:
    with pytest.raises(LoaderIsolationError, match="sqlite"):
        LiveFixtureLoader(tmp_path, database_backend="turso").load("cap_ux025")
