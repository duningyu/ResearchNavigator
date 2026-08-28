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

## Continuation run

`codex_audit/runs/20260828T_ENV_CLOSURE_CONT/` executed with Python 3.12 and uv 0.12.6:

- backend: **184 passed**;
- security/RAG: **16 passed**;
- frontend: **16 passed**, typecheck/build pass;
- MCP official stdio: **PASS**;
- Alembic: **0005 head, 53 tables, integrity ok**;
- compileall/OpenAPI: **PASS**;
- Ruff: **FAIL**, 63 findings;
- Mypy: **FAIL**, 8 findings;
- Docker, Playwright, live sources, OA, live LLM and real expert outcomes remain BLOCKED.
