from scripts.verify_delivery import render_command


def test_render_command_handles_a_sequence_of_commands() -> None:
    command = [["python", "seed.py"], ["python", "backup.py", "--force"]]

    assert render_command(command) == "python seed.py && python backup.py --force"


def test_blocked_check_uses_explicit_blocked_status() -> None:
    from scripts.verify_delivery import blocked

    result = blocked("frontend_build", "corepack pnpm run build", "dependencies unavailable")

    assert result["status"] == "BLOCKED"
    assert result["stderr"] == "dependencies unavailable"


def test_gap_ledger_tracks_2_2_implementation_separately_from_live_outcomes(tmp_path) -> None:
    import csv

    from scripts.verify_delivery import write_gap_ledger

    path = tmp_path / "gaps.csv"
    checks = [
        {"name": "backend_pytest", "status": "PASS", "stderr": ""},
        {"name": "evidence_platform_focused", "status": "PASS", "stderr": ""},
        {"name": "docker_harness_contract", "status": "PASS", "stderr": ""},
        {"name": "live_open_sources", "status": "BLOCKED", "stderr": "network unavailable"},
        {"name": "live_llm_provider", "status": "BLOCKED", "stderr": "not configured"},
        {"name": "docker_cold_start", "status": "BLOCKED", "stderr": "docker unavailable"},
    ]

    write_gap_ledger(path, checks)

    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = {row["gap_id"]: row for row in csv.DictReader(handle)}
    assert rows["GAP-010"]["status"] == "PASS"
    assert rows["GAP-011"]["status"] == "PASS"
    assert rows["GAP-012"]["status"] == "PASS"
    assert rows["GAP-014"]["status"] == "PASS"
    assert rows["GAP-007"]["status"] == "BLOCKED"
    assert rows["GAP-006"]["status"] == "SKIPPED"
