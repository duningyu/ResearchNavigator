# ResearchNavigator 2.2.0 Evidence Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a backwards-compatible, audited evidence workflow with lawful OA resolution, secure PDF ingestion, persistent source throttling, LLM enrichment, and historical abstract backfill.

**Architecture:** Keep FastAPI/SQLAlchemy/SQLite and use existing `Job`/`JobEvent` for versioned workflow execution. Add source-specific OA clients behind a resolver, a policy engine, and a redirect-safe streaming PDF fetcher. Deterministic analysis remains authoritative; optional LLM output is citation-validated and additive.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, SQLite, HTTPX, PyPDF, pytest.

**Spec:** `docs/superpowers/specs/2026-08-28-researchnavigator-2.2.0-evidence-platform-design.md`

## Global Constraints

- Preserve the existing `/papers/{paper_id}/acquire-evidence` response and semantics.
- Unknown or absent licenses are never auto-ingested.
- Every redirect hop is SSRF-validated; cookies and user credentials are never forwarded.
- Deterministic analysis always succeeds independently of optional provider availability.
- LLM fields require valid local citations and cannot exceed the current evidence level.
- Historical abstracts remain untrusted until exact-source reacquisition or lawful full-text upload.
- New user-scoped endpoints require cross-user denial tests.

---

### Task 1: Additive 0005 schema and ORM contracts

**Files:**
- Create: `apps/api/alembic/versions/0005_evidence_platform.py`
- Modify: `apps/api/research_navigator/models.py`
- Test: `tests/integration/test_evidence_platform_migration.py`

**Interfaces:**
- Produces `SourceRuntimeState`.
- Extends `PaperDocument`, `PaperAnalysisRecord`, and `ToolCall` with provenance/audit fields.
- Produces author, dataset, cluster, and expert-evaluation tables consumed by the next plan.

- [ ] Write a migration test that upgrades 0004 to head and asserts all new tables and columns.
- [ ] Run the migration test and verify failure because 0005 does not exist.
- [ ] Implement 0005 with an explicit downgrade and matching SQLAlchemy models.
- [ ] Run the migration test and full migration roundtrip tests.
- [ ] Commit `feat(db): add 2.2 evidence platform schema`.

### Task 2: Persist OpenAlex rate-limit state

**Files:**
- Modify: `apps/api/research_navigator/scholarly/base.py`
- Modify: `apps/api/research_navigator/scholarly/openalex.py`
- Create: `apps/api/research_navigator/scholarly/runtime.py`
- Modify: `apps/api/research_navigator/routes/search.py`
- Modify: `apps/api/research_navigator/routes/system.py`
- Test: `tests/unit/test_openalex_rate_limit.py`
- Test: `tests/integration/test_source_runtime_state.py`

**Interfaces:**
- Extends `SourceStatus` with `metadata: dict[str, object]`.
- Produces `SourceRuntimeRepository.before_call(source, now) -> SourceStatus | None` and `after_call(source, status, now) -> None`.
- OpenAlex adapter parses `X-RateLimit-*` headers and returns metadata without secrets.

- [ ] Write failing adapter tests for 429 metadata and successful rate-limit headers.
- [ ] Implement header parsing and bounded retry-after parsing.
- [ ] Write failing persistence tests for cooldown skip, recovery, and source-status API output.
- [ ] Implement the runtime repository and integrate it at the search API boundary.
- [ ] Verify that other adapters still run when OpenAlex is cooling down.
- [ ] Commit `feat(search): persist OpenAlex cooldown and fallback state`.

### Task 3: OA candidate resolver and policy engine

**Files:**
- Create: `apps/api/research_navigator/open_access/__init__.py`
- Create: `apps/api/research_navigator/open_access/base.py`
- Create: `apps/api/research_navigator/open_access/policy.py`
- Create: `apps/api/research_navigator/open_access/openalex.py`
- Create: `apps/api/research_navigator/open_access/unpaywall.py`
- Create: `apps/api/research_navigator/open_access/arxiv.py`
- Create: `apps/api/research_navigator/open_access/semantic_scholar.py`
- Create: `apps/api/research_navigator/open_access/resolver.py`
- Test: `tests/unit/test_oa_policy.py`
- Test: `tests/unit/test_oa_resolver.py`

**Interfaces:**
- Produces `OpenAccessCandidate` and `OpenAccessResolution` Pydantic models.
- Produces `decide_access(candidate) -> AccessDecision`.
- Produces `OpenAccessResolver.resolve(paper, *, audit) -> OpenAccessResolution`.

- [ ] Write policy RED tests for permissive, limited, unknown, paywalled, and credentialed URLs.
- [ ] Implement deterministic license normalization and decision rules.
- [ ] Write resolver RED tests using injected HTTPX transports for DOI and arXiv identities.
- [ ] Implement source clients and provenance hashes; never persist response bodies containing secrets.
- [ ] Run OA unit tests and commit `feat(oa): resolve lawful fulltext candidates`.

### Task 4: Redirect-safe PDF fetch and existing parser reuse

**Files:**
- Create: `apps/api/research_navigator/open_access/fetcher.py`
- Modify: `apps/api/research_navigator/documents/security.py`
- Modify: `apps/api/research_navigator/documents/parser.py`
- Modify: `apps/api/research_navigator/documents/index.py`
- Test: `tests/security/test_remote_pdf_fetcher.py`
- Test: `tests/integration/test_oa_pdf_ingestion.py`

**Interfaces:**
- Produces `SafePdfFetcher.fetch(candidate, destination) -> PdfFetchResult`.
- Reuses existing `parse_pdf` and `index_document` after policy and security pass.

- [ ] Write RED tests for private DNS, redirect-to-private, userinfo, HTML-as-PDF, wrong magic, oversized streams, and valid PDF.
- [ ] Implement per-hop URL/DNS checks and bounded streaming.
- [ ] Write an integration RED test that ingests a permissively licensed mock OA PDF and persists document provenance plus chunks.
- [ ] Implement OA document persistence without changing user-uploaded PDF behavior.
- [ ] Run security and PDF suites; commit `feat(oa): securely ingest permitted PDFs`.

### Task 5: Versioned evidence workflow API and worker handler

**Files:**
- Create: `apps/api/research_navigator/evidence/__init__.py`
- Create: `apps/api/research_navigator/evidence/workflow.py`
- Create: `apps/api/research_navigator/schemas/evidence.py`
- Create: `apps/api/research_navigator/routes/evidence.py`
- Modify: `apps/api/research_navigator/main.py`
- Modify: `services/worker/main.py`
- Test: `tests/integration/test_evidence_workflow.py`
- Test: `tests/integration/test_worker_evidence_workflow.py`

**Interfaces:**
- `POST /api/papers/{paper_id}/evidence-workflows` creates a `Job`.
- `POST /api/evidence-workflows/{job_id}/run` executes locally.
- `GET /api/evidence-workflows/{job_id}` returns ordered events and strongest evidence.
- `POST /api/evidence-workflows/{job_id}/cancel` uses existing cancellation semantics.
- Produces `execute_evidence_workflow(session, settings, job_id, adapters, provider) -> Job`.

- [ ] Write RED tests for create/read/run/cancel, cross-user denial, existing full-text bypass, abstract-only partial result, OA success, and failed external step preservation.
- [ ] Implement the ordered step executor and event helper.
- [ ] Register the worker handler using the same executor.
- [ ] Verify old `acquire-evidence` tests remain green.
- [ ] Commit `feat(evidence): add resumable acquisition workflow`.

### Task 6: LLM provider integration and citation audit

**Files:**
- Modify: `apps/api/research_navigator/config.py`
- Modify: `apps/api/research_navigator/analysis/providers.py`
- Create: `apps/api/research_navigator/analysis/llm_validation.py`
- Modify: `apps/api/research_navigator/analysis/service.py`
- Modify: `apps/api/research_navigator/routes/analysis.py`
- Modify: `apps/api/research_navigator/schemas/analysis.py`
- Test: `tests/unit/test_llm_analysis_validation.py`
- Test: `tests/integration/test_llm_analysis_api.py`

**Interfaces:**
- Adds `RN_ANALYSIS_PROVIDER`, `RN_ANALYSIS_PROMPT_VERSION`, and bounded provider timeout/retry settings.
- Produces `validate_and_merge_llm_analysis(deterministic, llm_output, accessible_chunks, evidence_level)`.
- `run_paper_analysis(..., provider_override=None)` returns/persists deterministic or hybrid analysis metadata.

- [ ] Write RED tests for valid additive fields, invalid JSON, missing citations, cross-paper chunks, abstract-level overreach, timeout fallback, and secret-free audit.
- [ ] Implement provider selection and validation.
- [ ] Persist analysis/provider/hash/fallback fields and extended `ToolCall` metadata.
- [ ] Verify deterministic default and old analysis API compatibility.
- [ ] Commit `feat(analysis): integrate citation-validated LLM enrichment`.

### Task 7: Historical abstract provenance backfill

**Files:**
- Create: `apps/api/research_navigator/evidence/backfill.py`
- Create: `apps/api/research_navigator/schemas/backfill.py`
- Create: `apps/api/research_navigator/routes/backfill.py`
- Modify: `apps/api/research_navigator/main.py`
- Modify: `services/worker/main.py`
- Test: `tests/integration/test_abstract_backfill.py`

**Interfaces:**
- `POST /api/admin/backfills/abstract-provenance` creates an admin job.
- `POST /api/admin/backfills/{job_id}/run` executes a batch locally.
- `GET /api/admin/backfills/{job_id}` returns categorized outcomes.
- Produces `execute_abstract_backfill(..., dry_run, batch_size, sources) -> dict[str, int]`.

- [ ] Write RED tests for admin-only, dry-run, exact DOI, exact arXiv, strict title+year, fixture rejection, conflict, idempotency, cancellation, resume, and no full-text downgrade.
- [ ] Implement the backfill job using existing evidence-acquisition matching rules.
- [ ] Register worker handler and rerun analysis only for verified updates.
- [ ] Commit `feat(evidence): backfill legacy abstract provenance safely`.
