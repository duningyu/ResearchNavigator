import json
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESET_SCRIPT = PROJECT_ROOT / "scripts" / "deployment" / "reset_public_demo.ps1"
MARKER_NAME = "PUBLIC_DEMO_RUNTIME.marker"
MARKER_KIND = "RESEARCH_NAVIGATOR_PUBLIC_DEMO_RUNTIME_V1"


def run_reset(data_dir: Path, *, validate_only: bool = False) -> subprocess.CompletedProcess[str]:
    command = [
        "pwsh",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(RESET_SCRIPT),
        "-ProjectRoot",
        str(PROJECT_ROOT),
        "-DemoDataDir",
        str(data_dir),
        "-StatePath",
        str(data_dir.parent / "isolated_public_demo_state.json"),
        "-PythonPath",
        sys.executable,
    ]
    if validate_only:
        command.append("-ValidateOnly")
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def write_marker(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    marker = {
        "marker": MARKER_KIND,
        "project_root": str(PROJECT_ROOT.resolve()),
        "created_at": "2026-08-31T00:00:00Z",
    }
    (data_dir / MARKER_NAME).write_text(json.dumps(marker), encoding="utf-8")


def combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout}\n{result.stderr}"


def test_reset_refuses_missing_marker_repository_drive_root_and_user_home(tmp_path: Path) -> None:
    missing_marker = run_reset(tmp_path / "unmarked", validate_only=True)
    assert missing_marker.returncode != 0
    assert "marker" in combined_output(missing_marker).lower()

    repository = run_reset(PROJECT_ROOT, validate_only=True)
    assert repository.returncode != 0
    assert "repository" in combined_output(repository).lower()

    drive_root = run_reset(Path(PROJECT_ROOT.anchor), validate_only=True)
    assert drive_root.returncode != 0
    assert "drive root" in combined_output(drive_root).lower()

    user_home = run_reset(Path.home(), validate_only=True)
    assert user_home.returncode != 0
    assert "user home" in combined_output(user_home).lower()


def test_reset_is_deterministic_and_preserves_only_fixture_demo_state(tmp_path: Path) -> None:
    data_dir = tmp_path / "ResearchNavigatorPublicDemo"
    write_marker(data_dir)

    first = run_reset(data_dir)
    assert first.returncode == 0, combined_output(first)
    first_receipt = json.loads((data_dir / "seed_receipt.json").read_text(encoding="utf-8"))

    second = run_reset(data_dir)
    assert second.returncode == 0, combined_output(second)
    second_receipt = json.loads((data_dir / "seed_receipt.json").read_text(encoding="utf-8"))

    semantic_keys = [
        "users",
        "projects",
        "papers",
        "favorites",
        "paper_sets",
        "comparisons",
        "analyses",
    ]
    assert {key: first_receipt[key] for key in semantic_keys} == {
        key: second_receipt[key] for key in semantic_keys
    }
    assert first_receipt["users"] == 1
    assert first_receipt["papers"] >= 3
    assert first_receipt["favorites"] >= 1
    assert first_receipt["paper_sets"] == 1
    assert first_receipt["comparisons"] == 1
    assert first_receipt["fixture_only"] is True
    assert first_receipt["real_world_validation_claimed"] is False

    database = data_dir / "research_navigator.db"
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
