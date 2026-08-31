import csv
import json
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "deployment" / "monitor_public_demo_soak.ps1"


def write_fixture(tmp_path: Path, elapsed: float = 40.0, stderr: str = "") -> tuple[Path, Path]:
    csv_path = tmp_path / "soak.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "timestamp",
                "elapsed_minutes",
                "vercel_http",
                "local_api_http",
                "tunnel_http",
                "worker_status",
                "errors_since_last_sample",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "timestamp": "2026-08-31T13:00:00+00:00",
                "elapsed_minutes": "0",
                "vercel_http": "200",
                "local_api_http": "200",
                "tunnel_http": "200",
                "worker_status": "ONLINE",
                "errors_since_last_sample": "",
            }
        )
        writer.writerow(
            {
                "timestamp": "2026-08-31T13:40:00+00:00",
                "elapsed_minutes": str(elapsed),
                "vercel_http": "200",
                "local_api_http": "200",
                "tunnel_http": "200",
                "worker_status": "ONLINE",
                "errors_since_last_sample": "",
            }
        )
    stderr_path = tmp_path / "soak.err"
    stderr_path.write_text(stderr, encoding="utf-8")
    return csv_path, stderr_path


def run_monitor(tmp_path: Path, *, elapsed: float, process_state: str, stderr: str = "") -> dict:
    csv_path, stderr_path = write_fixture(tmp_path, elapsed=elapsed, stderr=stderr)
    state_path = tmp_path / "state.json"
    result = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(SCRIPT),
            "-ProjectRoot",
            str(PROJECT_ROOT),
            "-SoakPid",
            "2416",
            "-TargetMinutes",
            "120",
            "-SoakCsv",
            str(csv_path),
            "-SoakStderr",
            str(stderr_path),
            "-StatePath",
            str(state_path),
            "-LogPath",
            str(tmp_path / "monitor.log"),
            "-RuntimePath",
            str(tmp_path / "runtime.json"),
            "-Once",
            "-SkipContextGuard",
            "-ProcessStateOverride",
            process_state,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(state_path.read_text(encoding="utf-8"))


def test_reads_csv_and_calculates_progress_without_mutating_source(tmp_path: Path) -> None:
    csv_path, _ = write_fixture(tmp_path, elapsed=40.0)
    before = csv_path.read_bytes()
    state = run_monitor(tmp_path, elapsed=40.0, process_state="RUNNING_MATCH")
    assert state["csv_row_count"] == 2
    assert state["elapsed_minutes"] == 40.0
    assert state["progress_percent"] == 33.33
    assert csv_path.read_bytes() == before


def test_matching_process_is_running(tmp_path: Path) -> None:
    assert run_monitor(tmp_path, elapsed=40.0, process_state="RUNNING_MATCH")["soak_process_state"] == "RUNNING"


def test_process_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    assert run_monitor(tmp_path, elapsed=40.0, process_state="RUNNING_MISMATCH")["monitor_status"] == "PROCESS_IDENTITY_MISMATCH"


def test_absent_process_before_target_is_early_exit(tmp_path: Path) -> None:
    assert run_monitor(tmp_path, elapsed=40.0, process_state="ABSENT")["monitor_status"] == "PROCESS_EXITED_EARLY"


def test_target_reached_while_process_alive_is_not_pass(tmp_path: Path) -> None:
    state = run_monitor(tmp_path, elapsed=120.0, process_state="RUNNING_MATCH")
    assert state["monitor_status"] == "TARGET_REACHED_PROCESS_STILL_RUNNING"
    assert state["monitor_status"] != "SOAK_PASS"


def test_target_reached_after_process_exit_requires_validation(tmp_path: Path) -> None:
    state = run_monitor(tmp_path, elapsed=120.0, process_state="ABSENT")
    assert state["monitor_status"] == "TARGET_REACHED_PENDING_TERMINAL_VALIDATION"
    assert state["terminal_validation_required"] is True


def test_fatal_stderr_is_warning_without_editing_csv(tmp_path: Path) -> None:
    csv_path, _ = write_fixture(tmp_path, elapsed=40.0)
    before = csv_path.read_bytes()
    state = run_monitor(tmp_path, elapsed=40.0, process_state="RUNNING_MATCH", stderr="Unhandled exception: database corrupt\n")
    assert state["monitor_status"] == "FATAL_LOG_DETECTED"
    assert state["stderr_status"] == "POTENTIAL_FATAL"
    assert csv_path.read_bytes() == before


def test_missing_csv_is_explicit_failure(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(SCRIPT), "-ProjectRoot", str(PROJECT_ROOT), "-SoakPid", "2416", "-SoakCsv", str(tmp_path / "missing.csv"), "-StatePath", str(state_path), "-LogPath", str(tmp_path / "monitor.log"), "-RuntimePath", str(tmp_path / "runtime.json"), "-Once", "-SkipContextGuard", "-ProcessStateOverride", "ABSENT"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(state_path.read_text(encoding="utf-8"))["monitor_status"] == "CSV_MISSING"


def test_status_command_prints_one_read_snapshot(tmp_path: Path) -> None:
    csv_path, _ = write_fixture(tmp_path, elapsed=40.0)
    deployment = tmp_path / "deployment"
    deployment.mkdir()
    csv_path.replace(deployment / "PUBLIC_DEMO_SOAK.csv")
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(PROJECT_ROOT / "scripts/deployment/show_public_demo_soak_progress.ps1"), "-ProjectRoot", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "40 / 120 min" in result.stdout
    assert "33.33%" in result.stdout


def test_soak_runner_has_terminal_receipt_and_heartbeat_hooks() -> None:
    source = (PROJECT_ROOT / "scripts/deployment/run_public_demo_soak.ps1").read_text(encoding="utf-8")
    assert "PUBLIC_DEMO_SOAK_TERMINAL.json" in source
    assert "PUBLIC_DEMO_SOAK_HEARTBEAT.json" in source
    assert "normal_completion" in source
