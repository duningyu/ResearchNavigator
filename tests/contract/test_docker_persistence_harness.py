from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_acceptance_compose_is_isolated_and_persists_runtime() -> None:
    compose = ROOT / "infra" / "docker-compose.acceptance.yml"
    assert compose.is_file()
    text = compose.read_text(encoding="utf-8")
    assert "rn-acceptance" in text
    assert "api:" in text and "worker:" in text and "web:" in text
    assert "RN_ACCEPTANCE_RUNTIME_DIR" in text
    assert "sqlite+pysqlite:////app/runtime/research_navigator.db" in text
    assert "RN_ENABLE_FIXTURE_SOURCE: \"true\"" in text
    assert "RN_ENABLE_OPENALEX: \"false\"" in text
    assert "condition: service_healthy" in text


def test_docker_persistence_verifier_has_cold_start_restart_backup_restore_gates() -> None:
    script = ROOT / "scripts" / "verify_docker_persistence.py"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    for expected in (
        "build",
        "--no-cache",
        "up",
        "--wait",
        "restart",
        "down",
        "stage-restore",
        "PRAGMA integrity_check",
        "runtime_sha256",
    ):
        assert expected in text


def test_missing_docker_is_reported_as_blocked_not_pass(tmp_path: Path) -> None:
    output = tmp_path / "docker-report.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_docker_persistence.py"),
            "--docker-executable",
            "definitely-missing-docker",
            "--runtime-dir",
            str(tmp_path / "runtime"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "BLOCKED"
    assert report["phases"]["docker_available"]["status"] == "BLOCKED"
