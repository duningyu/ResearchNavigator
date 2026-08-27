# ResearchNavigator 2.2.0 current verification report

Overall status: **PARTIAL**. Run: `codex_audit/runs/20260827T232244Z_RN220_ENV_CLOSURE`; commit: `8b39b55`.

| Gate | Status | Evidence |
|---|---|---|
| pnpm install --frozen-lockfile (10.15.1) | PASS | `pnpm-install-baseline.stdout.log` |
| Frontend typecheck | PASS after fix | `frontend-typecheck-green.stdout.log` |
| Frontend Vite build | PASS after fix | `frontend-build-green.stdout.log` |
| Frontend Vitest | FAIL (4 tests) | `frontend-vitest-baseline.stdout.log` |
| Python compileall (3.9 diagnostic) | PASS | `compileall-python39.exit` |
| uv lock/sync, pytest, Ruff, mypy | BLOCKED | uv unavailable; Python 3.9 unsupported |
| MCP/live sources/Docker | BLOCKED | runtime/dependency/Docker logs |

Historical PASS claims remain preserved in prior timestamped runs and were not reused as current evidence.
