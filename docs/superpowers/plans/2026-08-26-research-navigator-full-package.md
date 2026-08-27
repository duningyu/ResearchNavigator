# ResearchNavigator Full Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable local-first research assistant package with V1 paper workflow, V2 evidence-gap workflow, documentation, tests, Docker deployment files, and Codex completion harness.

**Architecture:** A React/TypeScript web application calls a FastAPI service backed by SQLite. External scholarly APIs are isolated behind adapters; document evidence is indexed through FTS5 and deterministic dense vectors; persistent jobs and workflows are stored in SQLite. Three stdio MCP servers expose bounded tools over the same domain services.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, SQLite/FTS5, HTTPX, PyPDF, React 19, TypeScript, Vite, Ant Design, TanStack Query, Vitest, Playwright, Docker Compose, MCP Python SDK v2.

**Spec:** `docs/superpowers/specs/2026-08-26-research-navigator-design.md`

## Global Constraints

- Never claim a candidate gap is proof of novelty.
- Never infer unavailable full-text details from metadata or abstract-only evidence.
- Preserve source provenance and raw record hashes.
- Persist user state outside containers.
- Mark all mock/fixture records explicitly.
- Do not hard-code secrets.
- Keep authorization-scoped data isolated by user_id.

---

### Task 1: Repository, configuration, and database kernel

**Files:**
- Create: `pyproject.toml`, `.env.example`, `apps/api/research_navigator/config.py`
- Create: `apps/api/research_navigator/db.py`, `apps/api/research_navigator/models.py`
- Test: `tests/unit/test_config.py`, `tests/unit/test_database.py`

**Interfaces:**
- Produces: `Settings`, `get_settings()`, `Base`, `SessionLocal`, `init_database()`.

- [ ] Write tests for environment configuration, SQLite WAL/foreign keys, timestamps, and user-scoped constraints.
- [ ] Run tests and verify RED because implementation modules do not exist.
- [ ] Implement configuration and database kernel.
- [ ] Run focused tests and verify GREEN.

### Task 2: Authentication and user-scoped CRUD

**Files:**
- Create: `apps/api/research_navigator/security.py`, `apps/api/research_navigator/auth.py`
- Create: `apps/api/research_navigator/schemas/auth.py`, `apps/api/research_navigator/schemas/projects.py`
- Test: `tests/unit/test_security.py`, `tests/integration/test_auth_projects.py`

**Interfaces:**
- Produces: password hashing, opaque session tokens, current-user dependency, profile/project CRUD APIs.

- [ ] Write tests for password hashing, token hashing, login/logout, and cross-user access denial.
- [ ] Verify RED.
- [ ] Implement minimal secure behavior.
- [ ] Verify GREEN.

### Task 3: Scholarly adapters, normalization, and deduplication

**Files:**
- Create: `apps/api/research_navigator/scholarly/base.py`
- Create: `apps/api/research_navigator/scholarly/openalex.py`, `crossref.py`, `arxiv.py`, `semantic_scholar.py`, `fixture.py`
- Create: `apps/api/research_navigator/scholarly/normalize.py`, `service.py`
- Test: `tests/unit/test_normalization.py`, `tests/unit/test_deduplication.py`, `tests/integration/test_search_api.py`

**Interfaces:**
- Produces: `PaperRecord`, `SearchRequest`, `ScholarlyAdapter`, `FederatedSearchService.search()`.

- [ ] Write failing tests for DOI/arXiv/title normalization, provenance, source errors, and deduplication.
- [ ] Implement adapters and federated search.
- [ ] Verify focused and integration tests.

### Task 4: Paper library, notes, tags, and persistence

**Files:**
- Create: `apps/api/research_navigator/library.py`, `schemas/library.py`
- Test: `tests/integration/test_library.py`

**Interfaces:**
- Produces: paper detail, favorite, note, tag, reading-status APIs.

- [ ] Write tests for persistence and user isolation.
- [ ] Implement routes/services.
- [ ] Verify tests.

### Task 5: PDF ingestion and hybrid evidence retrieval

**Files:**
- Create: `apps/api/research_navigator/documents/security.py`, `parser.py`, `index.py`, `retrieval.py`
- Test: `tests/unit/test_document_security.py`, `tests/unit/test_retrieval.py`, `tests/integration/test_pdf_ingestion.py`

**Interfaces:**
- Produces: safe upload validation, `DocumentChunk`, FTS5 indexing, dense hashing vectors, hybrid retrieval with citations.

- [ ] Write failing tests for MIME, size, filename, SSRF, chunking, lexical/dense ranking, and citation metadata.
- [ ] Implement minimal safe ingestion and retrieval.
- [ ] Verify tests.

### Task 6: Structured paper analysis, match score, and reproduction score

**Files:**
- Create: `apps/api/research_navigator/analysis/evidence.py`, `structured.py`, `matching.py`, `reproduction.py`
- Test: `tests/unit/test_evidence_boundaries.py`, `test_matching.py`, `test_reproduction.py`

**Interfaces:**
- Produces: evidence-aware `PaperAnalysis`, `DirectionMatch`, `ReproductionAssessment`.

- [ ] Write tests that reject unavailable fields and verify missing-aware weighted scores.
- [ ] Implement deterministic analysis and optional LLM provider interface.
- [ ] Verify tests.

### Task 7: V2 evidence matrix, challenge search, and planning

**Files:**
- Create: `apps/api/research_navigator/gaps/matrix.py`, `candidate.py`, `workflow.py`
- Create: `apps/api/research_navigator/plans/service.py`
- Test: `tests/unit/test_gap_candidate.py`, `tests/integration/test_gap_workflow.py`, `tests/integration/test_plans.py`

**Interfaces:**
- Produces: evidence matrix, bounded candidate gaps, challenge queries, confirmation gate, research plans.

- [ ] Write tests proving a gap cannot be confirmed before challenge search.
- [ ] Implement workflow states and audit records.
- [ ] Verify tests.

### Task 8: FastAPI composition, jobs, health, and source status

**Files:**
- Create: `apps/api/research_navigator/main.py`, `routes/*.py`, `jobs.py`
- Create: `services/worker/main.py`
- Test: `tests/integration/test_health_sources_jobs.py`

**Interfaces:**
- Produces: OpenAPI app, health endpoints, source health, persistent jobs, worker loop.

- [ ] Write endpoint tests.
- [ ] Implement app composition and worker.
- [ ] Verify tests.

### Task 9: MCP servers

**Files:**
- Create: `mcp_servers/scholarly_search/server.py`, `paper_access/server.py`, `research_workspace/server.py`
- Test: `tests/unit/test_mcp_contracts.py`, `tests/smoke/test_mcp_imports.py`

**Interfaces:**
- Produces: three stdio MCP servers with typed tools and provenance-rich outputs.

- [ ] Write contract tests.
- [ ] Implement tool schemas and bounded service calls.
- [ ] Verify imports and smoke tests.

### Task 10: React web application

**Files:**
- Create: `apps/web/package.json`, `apps/web/src/*`, `apps/web/tests/*`
- Test: Vitest component and utility tests; Playwright E2E specification.

**Interfaces:**
- Produces: auth, dashboard, projects, search, paper detail, library, comparison, gaps, plans, jobs, sources, settings, admin routes.

- [ ] Write frontend tests before source components.
- [ ] Implement API client, auth state, layout, routes, pages, and explainable score panels.
- [ ] Run typecheck, unit tests, and production build.

### Task 11: Docker, scripts, documentation, and release evidence

**Files:**
- Create: `infra/docker-compose.yml`, Dockerfiles, backup/restore scripts, README, PRD, TechDocs, ADRs, release notes, claim boundary.
- Test: `tests/contract/test_delivery_contract.py`

**Interfaces:**
- Produces: local/LAN deployment, persistent volumes, complete documentation and requirement traceability.

- [ ] Write delivery-contract tests checking mandatory files and no committed secrets.
- [ ] Add deployment and documentation artifacts.
- [ ] Validate YAML and scripts.

### Task 12: Verification, Codex harness, manifest, and ZIP

**Files:**
- Create: `CODEX_AUDIT_AND_COMPLETION_PROMPT.md`, `AGENTS.md`, `delivery/STATUS.json`, `delivery/SHA256SUMS.txt`, `delivery/TEST_REPORT.md`.

**Interfaces:**
- Produces: reproducible audit instructions and immutable package evidence.

- [ ] Run backend tests, lint/type checks where available, frontend tests/build, import smoke, and artifact contract.
- [ ] Record exact PASS/FAIL/NOT_RUN status without inflation.
- [ ] Generate SHA256 manifest excluding runtime and VCS data.
- [ ] Create final ZIP and verify its hash and file count.
