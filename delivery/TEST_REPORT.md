# ResearchNavigator 2.2.0 verification report

**Overall status: PARTIAL.**
Authoritative run: `codex_audit/runs/20260827T191732Z_RN220_FINAL`
Audited implementation commit: `a786c5b5359077b4fb63e7794cbb03bbc9d61f78`.

## Current executed PASS evidence

| Gate | Result | Evidence |
|---|---:|---|
| Full backend pytest | **184 passed in 68.30s** | `logs/backend_pytest_final.log` |
| New evidence-platform matrix | **42 passed in 14.89s** | `logs/evidence_platform_focused.log` |
| Security + RAG | **16 passed in 2.08s** | `logs/security_rag_final.log` |
| Alembic | **0001→0005, 53 tables, integrity ok** | `logs/alembic_upgrade_0005.log` |
| OpenAPI | **2.2.0, 83 paths, required paths present** | `OPENAPI.json`, `logs/openapi_contract.log` |
| Python compileall | **PASS** | `logs/compileall.log` |
| Frontend syntax | **41 TS/TSX PASS, syntax only** | `logs/frontend_syntax.log` |
| `uv lock --check` | **PASS** | `logs/uv_lock_check.log` |
| Backup/restore tests | **4 passed** | `logs/backup_restore.log` |
| Docker harness contracts | **3 passed** | `logs/docker_harness_contract.log` |
| Admin/backfill contracts | **7 passed** | `logs/admin_backfill_final.log` |

A first dedicated security/RAG invocation omitted the async plugin and failed six async tests for that invocation only; it is preserved as `logs/security_rag_without_async_plugin_failed.log`. The corrected command loaded `pytest_asyncio.plugin` and passed all 16 tests. This was a test-command configuration error, not a product-code regression.

## Current BLOCKED or SKIPPED evidence

- `uv sync --frozen --extra dev`: **BLOCKED** by DNS while fetching the locked `httpx2` package.
- Ruff and Mypy: **BLOCKED** because their executables could not be installed after the frozen sync failure.
- pnpm/typecheck/Vitest/Vite/Playwright: **BLOCKED** because Corepack could not resolve `registry.npmjs.org`; `node_modules` is absent.
- Docker cold start/restart/down-up/restore: **BLOCKED** because Docker is absent. The harness itself passed contract tests and emitted a machine-readable BLOCKED receipt.
- Official MCP stdio: **BLOCKED** because the `mcp` SDK is not installed and dependency sync is blocked.
- Live OpenAlex/Crossref/arXiv/Semantic Scholar: **BLOCKED** because all four current requests failed DNS resolution. No source is marked PASS from this run.
- Live OA ingestion: **BLOCKED** by the same network/access prerequisites.
- Live LLM provider: **BLOCKED** because provider URL/key/model were not configured.
- Real expert outcomes: **BLOCKED** until real external experts submit ratings.
- Real historical abstract backfill outcome: **BLOCKED** because this audit did not mutate an authorized historical runtime.
- Licensed commercial sources: **SKIPPED** without lawful credentials/contract scope.

## Claim boundary

Implementation tests prove code contracts, not current external availability or business/research outcomes. Lawful OA logic does not authorize every reachable PDF; fallback does not make OpenAlex live; mocked LLM tests are not live-provider evidence; expert infrastructure is not expert validation; and a backfill implementation does not mean historical records were actually promoted. The release is not production ready.
