#!/usr/bin/env python3
"""Execute ResearchNavigator release gates without inflating blocked checks into PASS."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile

try:
    from scripts.release_metadata import PACKAGE_NAME, PACKAGE_VERSION, RELEASE_LABEL
except ModuleNotFoundError:  # Direct ``python scripts/<name>.py`` invocation.
    from release_metadata import PACKAGE_NAME, PACKAGE_VERSION, RELEASE_LABEL

ROOT = Path(__file__).resolve().parents[1]


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run(
    name: str,
    command: list[str],
    *,
    timeout: int = 240,
    env: dict[str, str] | None = None,
    cwd: Path = ROOT,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "name": name,
            "status": "PASS" if completed.returncode == 0 else "FAIL",
            "command": command,
            "exit_code": completed.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": completed.stdout[-30000:],
            "stderr": completed.stderr[-30000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "status": "FAIL",
            "command": command,
            "exit_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": (exc.stdout or "")[-30000:] if isinstance(exc.stdout, str) else "",
            "stderr": f"Timed out after {timeout} seconds",
        }


def render_command(command: object) -> str:
    if isinstance(command, list):
        if command and all(isinstance(item, list) for item in command):
            return " && ".join(render_command(item) for item in command)
        return " ".join(str(item) for item in command)
    return str(command)


def blocked(name: str, command: list[str] | str, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "BLOCKED",
        "command": command,
        "exit_code": None,
        "duration_seconds": 0.0,
        "stdout": "",
        "stderr": reason,
    }


def skipped(name: str, command: list[str] | str, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "SKIPPED",
        "command": command,
        "exit_code": None,
        "duration_seconds": 0.0,
        "stdout": "",
        "stderr": reason,
    }


def git_value(*args: str) -> str:
    if not (ROOT / ".git").exists():
        return "unavailable: uploaded delivery contains no .git metadata"
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


def migration_check() -> dict[str, Any]:
    if not command_exists("alembic"):
        return blocked(
            "alembic_upgrade", ["alembic", "upgrade", "head"], "alembic executable is unavailable"
        )
    with tempfile.TemporaryDirectory(prefix="rn-alembic-") as temp_dir:
        database_path = Path(temp_dir) / "migration.db"
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{ROOT / 'apps/api'}:{ROOT}"
        env["RN_DATABASE_URL"] = f"sqlite+pysqlite:///{database_path.as_posix()}"
        result = run("alembic_upgrade", ["alembic", "upgrade", "head"], env=env)
        if result["status"] != "PASS":
            return result
        with sqlite3.connect(database_path) as connection:
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            session_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(search_sessions)")
            }
            gap_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(gap_candidates)")
            }
        required_tables = {
            "users",
            "papers",
            "search_sessions",
            "source_requests",
            "paper_sets",
            "paper_set_items",
            "comparison_runs",
            "gap_candidates",
            "gap_explanations",
            "idempotency_records",
            "user_settings",
            "jobs",
            "job_events",
            "source_runtime_states",
            "authors",
            "dataset_cards",
            "direction_cluster_runs",
            "evaluation_studies",
            "alembic_version",
        }
        required_session_columns = {
            "search_mode",
            "ranking_rule_version",
            "diversity_seed",
            "composition_json",
        }
        required_gap_columns = {"paper_set_id", "direction_snapshot_json"}
        missing_tables = sorted(required_tables - tables)
        missing_session_columns = sorted(required_session_columns - session_columns)
        missing_gap_columns = sorted(required_gap_columns - gap_columns)
        result.update(
            {
                "table_count": len(tables),
                "required_tables_missing": missing_tables,
                "required_search_session_columns_missing": missing_session_columns,
                "required_gap_columns_missing": missing_gap_columns,
            }
        )
        if missing_tables or missing_session_columns or missing_gap_columns:
            result["status"] = "FAIL"
            result["stderr"] += (
                f"\nMissing tables={missing_tables}; "
                f"search_session_columns={missing_session_columns}; "
                f"gap_columns={missing_gap_columns}"
            )
        return result


def backup_roundtrip_check() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="rn-backup-") as temp_dir:
        root = Path(temp_dir)
        runtime = root / "runtime"
        restored = root / "restored"
        export_path = root / "workspace.json"
        backup_path = root / "backup.zip"
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{ROOT / 'apps/api'}:{ROOT}"
        commands = [
            [
                sys.executable,
                "scripts/seed_demo.py",
                "--database",
                str(runtime / "research_navigator.db"),
                "--email",
                "verification@example.invalid",
                "--password",
                "verification-only-password-123",
            ],
            [
                sys.executable,
                "scripts/export_workspace.py",
                "--database",
                str(runtime / "research_navigator.db"),
                "--email",
                "verification@example.invalid",
                "--output",
                str(export_path),
            ],
            [
                sys.executable,
                "scripts/backup.py",
                "--runtime",
                str(runtime),
                "--output",
                str(backup_path),
            ],
            [
                sys.executable,
                "scripts/restore.py",
                str(backup_path),
                "--runtime",
                str(restored),
                "--force",
            ],
        ]
        started = time.monotonic()
        logs: list[dict[str, Any]] = []
        for command in commands:
            result = run("backup_roundtrip_step", command, env=env, timeout=120)
            logs.append(result)
            if result["status"] != "PASS":
                return {
                    "name": "backup_restore_export_roundtrip",
                    "status": "FAIL",
                    "command": commands,
                    "exit_code": result["exit_code"],
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "stdout": "\n".join(step["stdout"] for step in logs),
                    "stderr": "\n".join(step["stderr"] for step in logs),
                }
        payload = json.loads(export_path.read_text(encoding="utf-8"))
        with ZipFile(backup_path) as archive:
            entries = sorted(archive.namelist())
            manifest = json.loads(archive.read("backup-manifest.json"))
        with sqlite3.connect(restored / "research_navigator.db") as connection:
            users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            projects = connection.execute("SELECT COUNT(*) FROM research_projects").fetchone()[0]
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        valid = (
            payload["user"]["email"] == "verification@example.invalid"
            and "password_hash" not in export_path.read_text(encoding="utf-8").lower()
            and users == 1
            and projects == 1
            and integrity == "ok"
            and "research_navigator.db" in entries
            and int(manifest.get("format_version", 0)) >= 2
        )
        return {
            "name": "backup_restore_export_roundtrip",
            "status": "PASS" if valid else "FAIL",
            "command": commands,
            "exit_code": 0 if valid else 1,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": json.dumps(
                {
                    "export_email": payload["user"]["email"],
                    "archive_entries": entries,
                    "backup_format_version": manifest.get("format_version"),
                    "restored_users": users,
                    "restored_projects": projects,
                    "sqlite_integrity": integrity,
                    "credentials_omitted": "password_hash"
                    not in export_path.read_text(encoding="utf-8").lower(),
                },
                ensure_ascii=False,
            ),
            "stderr": "" if valid else "Roundtrip assertions failed",
        }


def acceptance_check(output_dir: Path, env: dict[str, str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="rn-http-acceptance-") as temp_dir:
        scenario_env = env.copy()
        scenario_env.update(
            {
                "RN_DATA_DIR": str(Path(temp_dir) / "runtime"),
                "RN_ENABLE_FIXTURE_SOURCE": "true",
                "RN_ENABLE_OPENALEX": "false",
                "RN_ENABLE_CROSSREF": "false",
                "RN_ENABLE_ARXIV": "false",
                "RN_ENABLE_SEMANTIC_SCHOLAR": "false",
                "RN_ENVIRONMENT": "verification",
            }
        )
        return run(
            "http_first_acceptance",
            [
                sys.executable,
                "scripts/run_acceptance_scenario.py",
                "--scenario-version",
                "feedback-closure-v1",
                "--output",
                str(output_dir / "HTTP_ACCEPTANCE.json"),
            ],
            env=scenario_env,
            timeout=180,
        )


def write_gap_ledger(path: Path, checks: list[dict[str, Any]]) -> None:
    by_name = {item["name"]: item for item in checks}

    def status(name: str, default: str = "BLOCKED") -> str:
        return str(by_name.get(name, {}).get("status", default))

    def evidence(name: str, default: str) -> str:
        item = by_name.get(name, {})
        return str(item.get("stderr") or item.get("stdout") or default)

    implementation = status("evidence_platform_focused", status("backend_pytest"))
    backend = status("backend_pytest")
    rows = [
        (
            "GAP-001",
            "Frontend dependency-aware typecheck/unit/build",
            "P0",
            status("frontend_typecheck"),
            evidence("frontend_typecheck", "not executed"),
            "Run corepack pnpm install --frozen-lockfile, then pnpm typecheck/test/build.",
        ),
        (
            "GAP-002",
            "Browser Playwright closed loop",
            "P0",
            status("playwright_e2e"),
            evidence("playwright_e2e", "not executed"),
            "Run the current API-backed Playwright flow including 2.2 evidence, map and evaluation pages.",
        ),
        (
            "GAP-003",
            "Docker cold start/restart/down-up/restore persistence",
            "P0",
            status("docker_cold_start"),
            evidence("docker_cold_start", "not executed"),
            "Run scripts/verify_docker_persistence.py on a Docker-capable host.",
        ),
        (
            "GAP-004",
            "Official MCP SDK stdio integration",
            "P0",
            status("mcp_stdio"),
            evidence("mcp_stdio", "not executed"),
            "Install locked dependencies and run scripts/verify_mcp_stdio.py against a local API.",
        ),
        (
            "GAP-005",
            "Live OpenAlex/Crossref/arXiv/Semantic Scholar smoke",
            "P0",
            status("live_open_sources"),
            evidence("live_open_sources", "not executed"),
            "Rerun with network and lawful keys; retain query/time/status/identifiers/provenance hashes.",
        ),
        (
            "GAP-006",
            "Licensed Web of Science/Elsevier/Scopus adapters",
            "P1",
            "SKIPPED",
            "No lawful credentials or authorized contract scope were supplied.",
            "Implement only after authorized access and source-specific contracts are available.",
        ),
        (
            "GAP-007",
            "Real expert outcome validation",
            "P1",
            status("real_expert_outcomes"),
            evidence("real_expert_outcomes", "No real external expert ratings were executed."),
            "Run a frozen, blinded real-expert study; simulated ratings cannot unlock this gate.",
        ),
        (
            "GAP-008",
            "Field and sentence citation attribution",
            "P1",
            backend,
            evidence("backend_pytest", "Current RAG/evidence tests"),
            "Do not misstate citation alignment as semantic entailment proof.",
        ),
        (
            "GAP-009",
            "Frozen uv dependency sync",
            "P0",
            status("uv_sync_frozen"),
            evidence("uv_sync_frozen", "not executed"),
            "Restore registry access and run uv sync --frozen --extra dev.",
        ),
        (
            "GAP-010",
            "LLM provider analysis API and audit persistence",
            "P1",
            implementation,
            evidence("evidence_platform_focused", "Provider merge/fallback/citation/audit tests"),
            "Validate a live provider separately; deterministic fallback remains default.",
        ),
        (
            "GAP-011",
            "Lawful OA full-text resolution and secure ingestion",
            "P1",
            implementation,
            evidence("evidence_platform_focused", "OA policy/resolver/fetcher/ingestion tests"),
            "Run a live lawful OA acquisition separately from deterministic tests.",
        ),
        (
            "GAP-012",
            "Author cards dataset cards direction clustering",
            "P1",
            implementation,
            evidence("evidence_platform_focused", "Author/dataset/cluster user-scope tests"),
            "Run current browser E2E when frontend dependencies are available.",
        ),
        (
            "GAP-013",
            "Bounded legacy summary evidence acquisition",
            "P0",
            backend,
            evidence("backend_pytest", "Compatibility endpoint tests"),
            "Keep /acquire-evidence backward compatible while full acquisition uses workflows.",
        ),
        (
            "GAP-014",
            "Historical abstract provenance backfill",
            "P1",
            implementation,
            evidence("evidence_platform_focused", "Dry-run/exact-match/idempotency/cancellation tests"),
            "Run dry-run on a real backup before any historical runtime mutation.",
        ),
        (
            "GAP-015",
            "OpenAlex persistent 429 cooldown and fallback",
            "P0",
            implementation,
            evidence("evidence_platform_focused", "Source runtime/rate-limit tests"),
            "OpenAlex live availability remains a separate gate.",
        ),
        (
            "GAP-016",
            "Evidence workflow terminal and worker semantics",
            "P0",
            implementation,
            evidence("evidence_platform_focused", "Workflow/worker partial/cancel tests"),
            "Monitor real worker execution after deployment.",
        ),
        (
            "GAP-017",
            "Docker persistence acceptance tooling implementation",
            "P0",
            status("docker_harness_contract"),
            evidence("docker_harness_contract", "Harness contract not executed"),
            "Tooling PASS does not replace GAP-003 actual Docker execution.",
        ),
        (
            "GAP-018",
            "Live LLM provider connectivity and stability",
            "P1",
            status("live_llm_provider"),
            evidence("live_llm_provider", "Provider not configured or not executed"),
            "Use lawful credentials and record model/prompt/latency/fallback without secrets.",
        ),
        (
            "GAP-019",
            "Real historical abstract backfill outcome",
            "P1",
            status("historical_backfill_outcome"),
            evidence("historical_backfill_outcome", "No real historical runtime was mutated"),
            "Run dry-run, review classifications, back up runtime, then execute explicitly.",
        ),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["gap_id", "requirement", "priority", "status", "evidence", "next_action"])
        writer.writerows(rows)


def write_check_logs(output_dir: Path, checks: list[dict[str, Any]]) -> None:
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    for check in checks:
        payload = [
            f"name={check['name']}",
            f"status={check['status']}",
            f"command={render_command(check['command'])}",
            f"exit_code={check['exit_code']}",
            f"duration_seconds={check['duration_seconds']}",
            "--- stdout ---",
            check["stdout"] or "(empty)",
            "--- stderr/blocker ---",
            check["stderr"] or "(empty)",
            "",
        ]
        (logs_dir / f"{check['name']}.log").write_text("\n".join(payload), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("delivery"))
    parser.add_argument("--run-live-sources", action="store_true")
    args = parser.parse_args()
    output_dir = (
        (ROOT / args.output_dir).resolve() if not args.output_dir.is_absolute() else args.output_dir
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT / 'apps/api'}:{ROOT}"
    checks: list[dict[str, Any]] = [
        run("backend_pytest", [sys.executable, "-m", "pytest", "-q"], timeout=360, env=env),
        run(
            "python_compileall",
            [
                sys.executable,
                "-m",
                "compileall",
                "-q",
                "apps/api",
                "services",
                "mcp_servers",
                "scripts",
            ],
            env=env,
        ),
        run(
            "openapi_export",
            [
                sys.executable,
                "scripts/export_openapi.py",
                "--output",
                str(output_dir / "OPENAPI.json"),
            ],
            env=env,
        ),
        migration_check(),
        backup_roundtrip_check(),
        acceptance_check(output_dir, env),
        run(
            "evidence_platform_focused",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "pytest_asyncio.plugin",
                "tests/integration/test_evidence_platform_migration.py",
                "tests/integration/test_source_runtime_state.py",
                "tests/integration/test_oa_pdf_ingestion.py",
                "tests/security/test_remote_pdf_fetcher.py",
                "tests/integration/test_evidence_workflow.py",
                "tests/integration/test_worker_evidence_workflow.py",
                "tests/integration/test_llm_analysis_api.py",
                "tests/unit/test_llm_analysis_validation.py",
                "tests/integration/test_abstract_backfill.py",
                "tests/integration/test_author_cards.py",
                "tests/integration/test_dataset_cards.py",
                "tests/integration/test_direction_clusters.py",
                "tests/integration/test_expert_evaluations.py",
            ],
            timeout=240,
            env=env,
        ),
        run(
            "docker_harness_contract",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/contract/test_docker_persistence_harness.py",
            ],
            timeout=120,
            env=env,
        ),
    ]

    if command_exists("ruff"):
        checks.append(
            run(
                "ruff",
                ["ruff", "check", "apps/api", "services", "mcp_servers", "scripts", "tests"],
                env=env,
            )
        )
    else:
        checks.append(blocked("ruff", "ruff check ...", "ruff executable is unavailable"))
    if command_exists("mypy"):
        checks.append(
            run("mypy", ["mypy", "apps/api/research_navigator", "services", "mcp_servers"], env=env)
        )
    else:
        checks.append(blocked("mypy", "mypy ...", "mypy executable is unavailable"))

    npm_root = (
        subprocess.run(
            ["npm", "root", "-g"], text=True, capture_output=True, check=False
        ).stdout.strip()
        if command_exists("npm")
        else ""
    )
    node_env = os.environ.copy()
    if npm_root:
        node_env["NODE_PATH"] = npm_root
    if command_exists("node"):
        checks.append(
            run(
                "frontend_syntax_transpile",
                ["node", "scripts/check_frontend_syntax.cjs", "apps/web"],
                env=node_env,
            )
        )
    else:
        checks.append(
            blocked(
                "frontend_syntax_transpile",
                "node scripts/check_frontend_syntax.cjs apps/web",
                "node executable is unavailable",
            )
        )

    web_root = ROOT / "apps/web"
    node_modules = web_root / "node_modules"
    if node_modules.is_dir():
        checks.extend(
            [
                run("frontend_typecheck", ["corepack", "pnpm", "run", "typecheck"], cwd=web_root),
                run("frontend_unit_tests", ["corepack", "pnpm", "test"], cwd=web_root),
                run("frontend_build", ["corepack", "pnpm", "run", "build"], cwd=web_root),
                run(
                    "playwright_e2e",
                    ["corepack", "pnpm", "run", "test:e2e"],
                    cwd=web_root,
                    timeout=360,
                ),
            ]
        )
    else:
        reason = (
            "apps/web/node_modules is absent and dependency installation cannot be "
            "completed in the current offline/DNS-constrained environment"
        )
        checks.extend(
            [
                blocked("frontend_typecheck", "corepack pnpm run typecheck", reason),
                blocked("frontend_unit_tests", "corepack pnpm test", reason),
                blocked("frontend_build", "corepack pnpm run build", reason),
                blocked("playwright_e2e", "corepack pnpm run test:e2e", reason),
            ]
        )

    if command_exists("docker"):
        checks.append(
            run(
                "docker_compose_config",
                ["docker", "compose", "-f", "infra/docker-compose.yml", "config"],
            )
        )
        checks.append(
            run(
                "docker_cold_start",
                [
                    sys.executable,
                    "scripts/verify_docker_persistence.py",
                    "--output",
                    str(output_dir / "DOCKER_PERSISTENCE.json"),
                ],
                timeout=900,
                env=env,
            )
        )
    else:
        checks.append(
            blocked(
                "docker_compose_config",
                "docker compose -f infra/docker-compose.yml config",
                "docker executable is unavailable",
            )
        )
        checks.append(
            blocked(
                "docker_cold_start", "docker compose up --build", "docker executable is unavailable"
            )
        )

    mcp_probe = run(
        "mcp_sdk_import",
        [sys.executable, "-c", "import mcp; print('official MCP SDK import PASS')"],
        env=env,
    )
    if mcp_probe["status"] == "PASS":
        checks.append(mcp_probe)
        checks.append(
            blocked(
                "mcp_stdio",
                f"{sys.executable} scripts/verify_mcp_stdio.py",
                "requires a separately started local API service; run as controlled integration",
            )
        )
    else:
        checks.append(
            blocked(
                "mcp_sdk_import",
                mcp_probe["command"],
                mcp_probe["stderr"] or "mcp SDK import failed",
            )
        )
        checks.append(
            blocked(
                "mcp_stdio",
                f"{sys.executable} scripts/verify_mcp_stdio.py",
                "official MCP SDK is unavailable",
            )
        )

    if args.run_live_sources:
        checks.append(
            run(
                "live_open_sources",
                [
                    sys.executable,
                    "scripts/verify_live_sources.py",
                    "--output",
                    str(output_dir / "LIVE_SOURCE_SMOKE.json"),
                ],
                env=env,
                timeout=180,
            )
        )
    else:
        checks.append(
            blocked(
                "live_open_sources",
                f"{sys.executable} scripts/verify_live_sources.py",
                "live network smoke was not requested; deterministic regression "
                "uses fixture sources",
            )
        )
    checks.append(
        skipped(
            "licensed_sources",
            "Web of Science / Elsevier / Scopus",
            "licensed adapters are outside the implemented source set and "
            "no lawful credentials were supplied",
        )
    )
    checks.append(
        blocked(
            "live_llm_provider",
            "configured OpenAI-compatible/Ollama smoke",
            "live provider smoke requires explicit lawful endpoint, model and credentials",
        )
    )
    checks.append(
        blocked(
            "real_expert_outcomes",
            "frozen blinded external-expert study",
            "no real external expert panel was executed in this release audit",
        )
    )
    checks.append(
        blocked(
            "historical_backfill_outcome",
            "admin historical abstract provenance backfill",
            "no real historical runtime was mutated in this release audit",
        )
    )
    if command_exists("uv") and (ROOT / "uv.lock").is_file():
        checks.append(
            run(
                "uv_sync_frozen",
                ["uv", "sync", "--frozen", "--extra", "dev"],
                timeout=240,
            )
        )
    else:
        checks.append(
            blocked(
                "uv_sync_frozen",
                "uv sync --frozen --extra dev",
                "uv executable or uv.lock is unavailable",
            )
        )

    if command_exists("uv") and (ROOT / "uv.lock").is_file():
        checks.append(run("uv_lock_check", ["uv", "lock", "--check"], timeout=120))
    elif (ROOT / "uv.lock").is_file():
        checks.append(blocked("uv_lock_check", "uv lock --check", "uv executable is unavailable"))
    else:
        checks.append(blocked("uv_lock_check", "uv lock --check", "uv.lock is absent"))

    failed = [check for check in checks if check["status"] == "FAIL"]
    blocked_checks = [check for check in checks if check["status"] == "BLOCKED"]
    skipped_checks = [check for check in checks if check["status"] == "SKIPPED"]
    overall = "FAIL" if failed else ("PARTIAL" if blocked_checks else "PASS")
    status = {
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "release_label": RELEASE_LABEL,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "audited_commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "working_tree_at_audit": git_value("status", "--short"),
        "overall_status": overall,
        "status_semantics": {
            "PASS": "acceptance command executed and its assertions passed in this run",
            "FAIL": "acceptance command executed and failed in this run",
            "BLOCKED": (
                "required executable, dependency, credentials, network, "
                "or controlled runtime was unavailable"
            ),
            "SKIPPED": "explicitly outside the implemented/authorized scope for this release",
        },
        "checks": checks,
        "known_boundaries": [
            "Candidate research gaps and Gap Explanation Agent outputs are "
            "evidence-bounded hypotheses, not proof of novelty.",
            "simulated_human_confirmation is an automated acceptance action "
            "and is never reported as expert review.",
            "Fixture papers are deterministic offline test records, not scholarly evidence.",
            "Live source smoke is non-deterministic: retain query/time/source status/stable "
            "identifiers/raw response hashes rather than fixed titles or counts.",
            "Abstract-only analysis does not support full-text experimental protocol, "
            "Future Work, or author-stated limitation claims.",
            "Field citation locations currently preserve supplied page/chunk provenance; "
            "they are not sentence-level entailment proof.",
            "Search diversity is seeded within relevance bands and remains reproducible "
            "per saved session; it is not unrestricted randomization.",
            "Unknown OA rights never trigger automatic full-text storage; a PDF URL is not sufficient.",
            "OpenAlex fallback success does not relabel OpenAlex itself as healthy.",
            "Citation-validated provider tests do not prove a live LLM endpoint is available.",
            "Author name-only identities remain unresolved; dataset fields are not inferred from names.",
            "Direction clusters are literature-organization aids, not objective field taxonomy.",
            "Evaluation infrastructure does not prove expert effectiveness; simulated ratings remain separate.",
            "The package is a local/LAN research workflow implementation, "
            "not a verified public SaaS deployment.",
        ],
    }
    (output_dir / "STATUS.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_gap_ledger(output_dir / "GAP_LEDGER.csv", checks)
    write_check_logs(output_dir, checks)

    lines = [
        f"# {PACKAGE_NAME} {PACKAGE_VERSION} Verification Report",
        "",
        f"- Generated (UTC): `{status['generated_at_utc']}`",
        f"- Git metadata: `{status['audited_commit']}`",
        f"- Overall status: **{overall}**",
        "",
        "`PARTIAL` means deterministic gates passed but at least one required "
        "environment-dependent gate is BLOCKED. It is not equivalent to production readiness.",
        "",
        "## Check matrix",
        "",
        "| Check | Status | Exit | Duration | Command / blocker |",
        "|---|---:|---:|---:|---|",
    ]
    for check in checks:
        detail = (
            check["stderr"]
            if check["status"] in {"BLOCKED", "SKIPPED"}
            else render_command(check["command"])
        )
        lines.append(
            f"| `{check['name']}` | **{check['status']}** | {check['exit_code']} "
            f"| {check['duration_seconds']}s | {detail.replace('|', '/')} |"
        )
    lines.extend(["", "## Exact outputs", ""])
    for check in checks:
        lines.extend(
            [
                f"### {check['name']} — {check['status']}",
                "",
                "```text",
                (check["stdout"] or check["stderr"] or "(no output)").rstrip(),
                "```",
                "",
            ]
        )
    lines.extend(
        ["## Claim boundary", "", *[f"- {item}" for item in status["known_boundaries"]], ""]
    )
    (output_dir / "TEST_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "overall_status": overall,
                "checks": len(checks),
                "failed": len(failed),
                "blocked": len(blocked_checks),
                "skipped": len(skipped_checks),
            },
            ensure_ascii=False,
        )
    )
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
