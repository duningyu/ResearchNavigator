import json
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GUARD = PROJECT_ROOT / "scripts" / "deployment" / "assert_researchnavigator_context.ps1"


def run_guard(root: Path, *, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    arguments = [
        "pwsh",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(GUARD),
        "-ProjectRoot",
        str(root),
    ]
    if quiet:
        arguments.append("-Quiet")
    return subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def commit_fixture(root: Path) -> None:
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=test@example.invalid", "-c", "user.name=Test", "commit", "-m", "fixture"],
        check=True,
        capture_output=True,
    )


def test_verified_researchnavigator_root_passes_context_guard() -> None:
    result = run_guard(PROJECT_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESEARCHNAVIGATOR_CONTEXT=PASS" in result.stdout


def test_quiet_context_guard_does_not_write_to_stdout() -> None:
    result = run_guard(PROJECT_ROOT, quiet=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == ""


def test_insightforge_like_root_is_refused(tmp_path: Path) -> None:
    insightforge_root = tmp_path / "insightforge_closed_beta"
    insightforge_root.mkdir()
    result = run_guard(insightforge_root)
    assert result.returncode != 0
    assert "INSIGHTFORGE_ROOT_REFUSED" in result.stderr


def test_wrong_lineage_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "rn-wrong-lineage"
    (root / "deployment").mkdir(parents=True)
    (root / "scripts" / "deployment").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nversion = "2.2.3"\n', encoding="utf-8")
    (root / "scripts" / "deployment" / "start_public_demo.ps1").write_text("", encoding="utf-8")
    (root / "deployment" / "PUBLIC_DEMO_DEPLOYMENT_RECEIPT.json").write_text(
        json.dumps({"version": "2.2.3"}), encoding="utf-8"
    )
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    commit_fixture(root)
    result = run_guard(root)
    assert result.returncode != 0
    assert "LINEAGE_MISMATCH" in result.stderr


def test_missing_product_fingerprint_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "rn-missing-fingerprint"
    (root / "deployment").mkdir(parents=True)
    (root / "scripts" / "deployment").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nversion = "2.2.3"\n', encoding="utf-8")
    (root / "scripts" / "deployment" / "start_public_demo.ps1").write_text("", encoding="utf-8")
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    commit_fixture(root)
    result = run_guard(root)
    assert result.returncode != 0
    assert "LINEAGE_MISMATCH" in result.stderr or "FINGERPRINT_MISSING" in result.stderr


def test_mutating_public_demo_scripts_invoke_context_guard() -> None:
    scripts = (
        "start_public_demo.ps1",
        "stop_public_demo.ps1",
        "status_public_demo.ps1",
        "reset_public_demo.ps1",
        "reconcile_public_demo_state.ps1",
        "restart_public_demo_component.ps1",
        "run_public_demo_soak.ps1",
    )
    for name in scripts:
        content = (PROJECT_ROOT / "scripts" / "deployment" / name).read_text(encoding="utf-8")
        assert "assert_researchnavigator_context.ps1" in content, name
