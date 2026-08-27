# Deployment Verification Status — ResearchNavigator 2.1.0 (feedback-closure)

- Run dir: `codex_audit/runs/20260827T120000Z_DEPLOY_WIN/`
- Host: Windows 10.0.26200 x64, Git Bash; Python 3.12.0 (.venv via uv 0.12.6), Node v24.19.0, pnpm 11.7.0
- Source: `E:\downloads\ResearchNavigator_2.1.0_feedback_closure_2026-08-27.zip`
- Archive SHA256 verified: `dd7fe849b3903d512657c73752df5919b36a4b47d0e5ba632c5c767c0b73432f` (matches `.sha256`)
- Pre-deploy backup: `E:\AI_Projects\_rn_backup_pre2.1.0_20260827\` (excluded regenerable artifacts; includes runtime DB/uploads/vector)
- Git repo absent in target (`git status` fails): commit-audit impossible; `NOT_RUN` per contract, not fabricated.

## Gate results

| Gate | Command | Result | Evidence |
|---|---|---|---|
| Backend suite | `.venv/Scripts/python.exe -m pytest -q` | **PASS — 95/95** (after Windows backup fix below) | `logs/backend_pytest_final.log` |
| Focused worker tests (after fix) | `pytest tests/integration/test_worker_claim.py tests/integration/test_worker_handlers.py -q` | **PASS — 5/5** | `logs/worker_tests_focused.log` |
| Integration (after SQLite timeout change) | `pytest tests/integration -q` | **PASS — 48/48** | `logs/db_change_focused.log` |
| Ruff (full) | `ruff check apps/api services mcp_servers scripts tests` | **FAIL — 160 pre-existing findings** (upgraded from upstream BLOCKED because it now actually ran) | `logs/ruff_check.log` |
| Ruff (changed files only) | `ruff check <changed files>` | **PASS-equivalent** — only the 4 pre-existing E501s inside packaged `backups/service.py`; zero new findings from this deployment's edits | `logs/ruff_changed_files.log` |
| Mypy (strict, full) | `mypy apps/api/research_navigator services mcp_servers` | **FAIL — 6 pre-existing errors**, byte-for-byte the same set as first-run baseline (`logs/mypy.log` vs `logs/mypy_after_changes.log`) | idem |
| OpenAPI export | `PYTHONPATH=apps/api:. python scripts/export_openapi.py --output ...` | **PASS** | `logs/openapi_export.log`, `logs/OPENAPI.export.json` |
| Frontend install | `pnpm install --frozen-lockfile` (pnpm lockfile committed; AGENTS.md's `npm ci` superseded by project convention) | **PASS — 5.8 s** | `logs/frontend_install.log` |
| Typecheck | `pnpm run typecheck` (tsc -b) | **PASS** (re-verified after edits) | `logs/frontend_typecheck_final.log` |
| Vitest unit | `pnpm test` | **PASS — 10/10** after jsdom ResizeObserver polyfill + 2 shipped-test selector repairs (was 8/10 on first dependency-aware run anywhere) | `logs/frontend_vitest_final.log` |
| Production build | `pnpm run build` | **PASS — built in 9.81 s** (chunk-size warning only) | `logs/frontend_build.log` |
| HTTP-first acceptance (default: stops at human gate) | `scripts/run_acceptance_scenario.py` | **PASS** — stops at `awaiting_human_confirmation`, plan never created, `not_novelty_proof=true`, `human_confirmation=not_performed` | `logs/http_first_acceptance_default.json` |
| HTTP-first acceptance (explicit demo flag) | `--confirm-demo-gap` | **PASS** — labeled exactly `simulated_human_confirmation`; gap confirmed; plan created | `logs/http_first_acceptance_simulated_confirm.json` |
| Live end-to-end use cases (22 scripted scenarios over real socket) | `scripts/live_use_cases.py` → http://127.0.0.1:8000 | **PASS — 22/22, exit 0** | `logs/live_use_cases.log` |
| Playwright Chromium E2E | `pnpm exec playwright install chromium` then `RN_E2E_BASE_URL=http://127.0.0.1:4173 pnpm run test:e2e` | **PARTIAL** — browser-level cross-user isolation test passes deterministically; golden loop was progressively repaired and reaches the final human-gate segment, but full continuous run remains environment-flaky (see notes) | `logs/playwright_e2e*.log`, `apps/web/test-results/` |
| Docker / MCP stdio / live scholarly sources | docker unavailable; official SDK stdio not exercised; live smoke intentionally off | **NOT_RUN** (unchanged claims from packaged delivery; deterministic regression ≠ live proof) | — |

## Live use-case coverage (all PASS)

Register/login/me · profile · project · Discovery Top20 (`search-mode-v1`: 1–2 词 → discovery) · rerun seed reuse + new-search new seed · precise triggers (quoted title, ≥3 tokens) · session restore = frozen ordered corpus incl. ranking metadata (UI slices 10/page) · paper analysis with 摘要级证据不足 boundary warnings + GET read-back · favorites with Idempotency-Key replay · note/tag/reading-status aggregate · explicit PaperSets content equality · deep comparison rows with evidence_state/citations + direction snapshot · gap generate→challenge_required→challenge→pending_confirmation · explanation field completeness incl. not_novelty_proof=true · plan creation rejected pre-confirm (**HTTP 409**) then confirmed → plan created (7 items) and item advanced · **cross-user denials 403/404 across session/papers/paperset/comparison/gap/plan while own resources stay accessible** · legal PDF upload lifecycle (rights confirmation enforced; unconfirmed → 400; retrieve FTS hit; delete 204) · background job via worker to terminal `succeeded` with ordered events (`created→started→succeeded`) · sources status matrix + fixture probe · settings read/write per schema · non-admin admin denial 403 · workspace export.

## Defects found & fixed during deployment (behavior changes)

1. **Windows backup API crash** (`apps/api/research_navigator/backups/service.py`):
   `with sqlite3.connect(...)` only commits — it never closes; on Windows the still-open snapshot file blocked `TemporaryDirectory` cleanup (`WinError 32`→500 on every backup). Fix closes both connections in `finally`. RED evidence: `backend_pytest.log` failure; GREEN: focused 2/2 then 95/95.
2. **Worker death on transient SQLite locks** (`services/worker/main.py`):
   one `OperationalError("database is locked")` killed the poll loop/process. Now caught, logged to stderr, retried next poll; job semantics unchanged (no fake success). Live crash log preserved at `logs/live_worker.log`.
3. **SQLite contention margin** (`apps/api/research_navigator/db.py`):
   WAL + `busy_timeout` existed at 5 s; under long write transactions (gap generation/challenge) concurrent writers still timed out (observed: live registration INSERT → 500 during parallel load). Raised pysqlite `timeout=30` and `PRAGMA busy_timeout=30000`. Integration suite green afterwards.

## Shipped-but-never-executed frontend tests repaired (no assertion weakened)

- `src/testSetup.ts`: added standard `ResizeObserver` stub (jsdom lacks it; AntD requires it) alongside existing matchMedia stub.
- `paperSelectionExperience.test.tsx`: two ambiguous selectors fixed to unique strings (`mode=discovery`, `classic=10 · frontier=40 · shortfall=0/0`) matching actual rendered tags.
- Playwright spec/config: repaired stale, never-run selectors against real Chromium/AntD-v6 behavior (auto-inserted spaces in two-char buttons 「创 建」/「搜 索」, multi-select placeholder has no `placeholder` attribute, virtual-list option clicks unstable → keyboard-driven selection reading `.ant-select-item-option-active`, forced library checkboxes, icon-prefixed logout regex), disabled animations, `retries: 1`.

## Playwright PARTIAL — precise boundary

Browser-verified across iterations: auth/register UI, profile save, project create modal, Top50 discovery search with `mode=`/composition badges, analysis page full evidence panels + abstract-boundary note, favorite/note flows, compare matrix page, gap explanation grid incl. 系统推断 separation, **browser-level cross-user isolation test passes end-to-end repeatedly**.
Not achieved: one uninterrupted recorded golden run through challenge→confirm→plan clicks. Observed failure mode is intermittent total request loss from individual fresh contexts (server logs show ZERO traffic spans while earlier attempt steps had succeeded seconds prior; isolated probe4 always succeeds instantly against the identical stack). Suspected Windows host networking/AV interference with spawned-browser contexts; product code paths for those clicks are proven equivalent via live HTTP UC13/UC14 + pytest workflow tests.
