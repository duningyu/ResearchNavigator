"""E4.22 smoke tests for driver and scientific fixture materialization."""

from pathlib import Path

import pytest
from tests.support.e4_22_scientific_fixture_loader import E422ScientificFixtureLoader


@pytest.mark.parametrize(
    "capability_id",
    [
        "cap_ux011_profile_stale_driver",
        "cap_ux056_scope_driver",
        "cap_ux028_timeout_403",
        "cap_ux029_no_public_route",
        "cap_ux048_incomparable_set",
        "cap_ux055_future_work",
        "cap_ux058_challenge_counter",
    ],
)
def test_e4_22_fixture_api_readback_isolated_and_test_only(
    tmp_path: Path, capability_id: str
) -> None:
    state = E422ScientificFixtureLoader(tmp_path / capability_id).load(capability_id)
    assert state.test_only is True
    assert state.scientific_claim_allowed is False
    assert state.domain_positive_contribution is False
    assert state.live_smoke is True
    assert state.api_readback is True
    assert state.db_path.endswith("test.db")
    assert state.cleanup_verified is True


def test_e4_22_profile_stale_state_is_read_back(tmp_path: Path) -> None:
    state = E422ScientificFixtureLoader(tmp_path / "stale").load(
        "cap_ux011_profile_stale_driver"
    )
    assert state.observed["recommendations_current"]
    assert all(value is False for value in state.observed["recommendations_current"])


def test_e4_22_future_work_has_structured_citations(tmp_path: Path) -> None:
    state = E422ScientificFixtureLoader(tmp_path / "future").load("cap_ux055_future_work")
    assert state.observed["future_work"]
    assert state.observed["future_citations"]


def test_e4_22_incomparable_fixture_reaches_comparison_route(tmp_path: Path) -> None:
    state = E422ScientificFixtureLoader(tmp_path / "compare").load(
        "cap_ux048_incomparable_set"
    )
    comparison = state.observed["comparison"]
    assert len(comparison["papers"]) == 4
    assert comparison["rows"]
