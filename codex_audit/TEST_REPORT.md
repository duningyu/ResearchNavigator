# ResearchNavigator 2.2.0 environment-closure audit

Run: `codex_audit/runs/20260827T232244Z_RN220_ENV_CLOSURE`  
Commit: `8b39b55`

## Executed results

| Check | Status | Evidence |
|---|---|---|
| pnpm install --frozen-lockfile (pnpm 10.15.1) | PASS | `pnpm-install-baseline.stdout.log` |
| frontend typecheck (baseline) | FAIL | `frontend-typecheck-baseline.stdout.log` |
| frontend typecheck (after fix) | PASS | `frontend-typecheck-green.stdout.log` |
| frontend build (after fix) | PASS | `frontend-build-green.stdout.log` |
| frontend Vitest | FAIL (4 tests) | `frontend-vitest-baseline.stdout.log` |
| frontend syntax | BLOCKED/FAIL: missing TypeScript before install | `frontend-syntax-baseline.stderr.log` |
| Python compileall (Python 3.9 diagnostic) | PASS | `compileall-python39.exit` |
| uv lock/sync, pytest, Ruff, mypy | BLOCKED: uv unavailable | corresponding `uv-*`, `pytest-*`, `ruff-*`, `mypy-*` logs |
| MCP/live-source/Docker scripts | BLOCKED: Python 3.9 or missing mcp/Docker | corresponding `*-baseline2` logs |

Historical delivery and audit reports were treated as claims only.
