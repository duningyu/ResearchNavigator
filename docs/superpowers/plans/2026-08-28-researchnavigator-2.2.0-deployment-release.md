# ResearchNavigator 2.2.0 Deployment and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reproducible Docker restart-persistence acceptance, close documentation/traceability, run current-environment gates, and produce an evidence-bounded 2.2.0 release package.

**Architecture:** Use a dedicated acceptance compose project and HTTP-first verification script. Preserve runtime state in named volumes, verify restart/down-up/backup-restore behavior, and record every command as PASS/FAIL/BLOCKED/SKIPPED. Package only source, migrations, tests, fixtures, and reports—never runtime databases, secrets, or downloaded full text.

**Tech Stack:** Docker Compose, Python, FastAPI HTTP API, SQLite integrity checks, pnpm/Vite/Vitest/Playwright, pytest, Ruff, Mypy.

**Spec:** `docs/superpowers/specs/2026-08-28-researchnavigator-2.2.0-evidence-platform-design.md`

## Global Constraints

- Docker is PASS only after real current-checkout build/start/restart/down/up assertions.
- Live sources remain separately reported; fixture regression cannot establish live integration.
- Real-expert validation remains BLOCKED until real external ratings exist.
- Release ZIP excludes `.env`, runtime data, PDFs, API keys, browser state, and licensed content.

---

### Task 1: Docker persistence harness

**Files:**
- Create: `infra/docker-compose.acceptance.yml`
- Create: `scripts/verify_docker_persistence.py`
- Create: `tests/contract/test_docker_acceptance_contract.py`
- Modify: `docs/deployment-runbook.md`

**Interfaces:**
- Script executes HTTP-first seed, restart, down/up, backup/restore, file/hash, and SQLite checks.

- [ ] Write RED contract tests for required compose services, volumes, health checks, and script stages.
- [ ] Implement compose override and verification script.
- [ ] Run contract tests; run Docker acceptance if executable exists, otherwise record exact BLOCKED evidence.
- [ ] Commit `test(docker): add restart persistence acceptance`.

### Task 2: Frontend workflow progress and missing-state closure

**Files:**
- Modify: `apps/web/src/types/domain.ts`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/pages/PaperPage.tsx`
- Modify: `apps/web/src/pages/JobsPage.tsx`
- Test: `apps/web/src/pages/EvidenceWorkflow.test.tsx`

**Interfaces:**
- UI creates/polls/cancels evidence workflow and renders every step, source, failure reason, evidence promotion, missing fields, provider/fallback, and final status.

- [ ] Write RED rendering tests for metadata-only, partial abstract, OA success, rate-limited source, LLM fallback, and missing-fields visibility.
- [ ] Implement progress timeline and robust empty/error states.
- [ ] Run frontend gates and commit `fix(web): show evidence workflow and missing states`.

### Task 3: Acceptance, documentation, and release package

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/architecture.md`
- Modify: `docs/api-design.md`
- Modify: `docs/database-design.md`
- Modify: `docs/data-source-contracts.md`
- Modify: `docs/requirement-traceability.md`
- Modify: `docs/claim-boundary.md`
- Modify: `delivery/STATUS.json`
- Modify: `delivery/TEST_REPORT.md`
- Create: `codex_audit/runs/<timestamp>/...`

**Interfaces:**
- Version becomes `2.2.0`.
- Final ledgers separate implemented behavior from environment/live/expert verification.

- [ ] Run focused and full backend tests, security/RAG tests, migrations, compile, Ruff, and Mypy.
- [ ] Run frontend frozen install/typecheck/Vitest/build/Playwright when available.
- [ ] Run OpenAPI, MCP stdio, live-source, Docker, backup/restore, and package-integrity commands.
- [ ] Record exact outputs and blockers; update traceability and claim boundary only from those outputs.
- [ ] Build ZIP plus SHA256 and package report; independently verify archive integrity.
- [ ] Commit `release: prepare ResearchNavigator 2.2.0 evidence platform`.
