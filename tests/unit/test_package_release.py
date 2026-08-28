import csv
import json
from pathlib import Path

from scripts.package_release import should_exclude


def test_package_excludes_runtime_secrets_caches_and_existing_hash_outputs() -> None:
    excluded = [
        Path(".git/config"),
        Path(".venv/bin/python"),
        Path("apps/api/__pycache__/module.pyc"),
        Path("apps/web/node_modules/react/index.js"),
        Path("runtime/research_navigator.db"),
        Path(".env"),
        Path("delivery/SHA256SUMS.txt"),
        Path("delivery/FILE_MANIFEST.json"),
    ]
    included = [
        Path(".env.example"),
        Path("runtime/.gitkeep"),
        Path("apps/api/research_navigator/main.py"),
        Path("delivery/STATUS.json"),
    ]

    assert all(should_exclude(path) for path in excluded)
    assert not any(should_exclude(path) for path in included)


def test_release_metadata_is_consistent_across_generated_delivery_artifacts() -> None:
    from scripts.package_release import PACKAGE_VERSION, RELEASE_LABEL

    package_info = json.loads((Path("delivery") / "PACKAGE_INFO.json").read_text())
    status = json.loads((Path("delivery") / "STATUS.json").read_text())

    assert package_info["package_version"] == PACKAGE_VERSION
    assert package_info["release_label"] == RELEASE_LABEL
    assert RELEASE_LABEL in package_info["claim"]
    assert status["package_version"] == PACKAGE_VERSION
    assert status["release_label"] == RELEASE_LABEL


def test_delivery_gap_ledger_does_not_reopen_currently_passed_gates() -> None:
    status = json.loads((Path("delivery") / "STATUS.json").read_text())
    with (Path("delivery") / "GAP_LEDGER.csv").open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        gaps = {row["gap_id"]: row for row in csv.DictReader(handle)}

    pass_requirements = {
        "GAP-001": {"frontend_typecheck", "vitest_10", "vite_build"},
        "GAP-002": {"playwright_2"},
        "GAP-004": {"mcp_official_stdio_full_matrix"},
    }
    passed = set(status["pass"])
    for gap_id, required_checks in pass_requirements.items():
        if required_checks <= passed:
            assert gaps[gap_id]["status"] == "PASS", (
                f"{gap_id} reopens checks already marked PASS: {sorted(required_checks)}"
            )


def test_release_version_is_2_2_2_across_runtime_and_packages() -> None:
    import tomllib

    from scripts.release_metadata import PACKAGE_VERSION, RELEASE_LABEL

    from research_navigator.main import app

    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    web_package = json.loads(Path("apps/web/package.json").read_text(encoding="utf-8"))

    assert PACKAGE_VERSION == "2.2.2"
    assert RELEASE_LABEL == "evidence-platform"
    assert pyproject["project"]["version"] == PACKAGE_VERSION
    assert web_package["version"] == PACKAGE_VERSION
    assert app.version == PACKAGE_VERSION
