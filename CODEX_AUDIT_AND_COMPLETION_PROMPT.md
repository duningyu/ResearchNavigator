# Codex Audit and Completion Prompt — ResearchNavigator

You are receiving a complete ResearchNavigator engineering package produced in a constrained build environment. Your task is **not** to praise, cosmetically reformat, or blindly continue it. Your task is to independently audit every claim, identify gaps against the approved master specification, implement the highest-priority missing or defective behavior, and leave reproducible evidence.

## 0. Non-negotiable sources

Read these files before any edit:

1. `docs/APPROVED_MASTER_PROMPT.txt`
2. `AGENTS.md`
3. `docs/superpowers/specs/2026-08-26-research-navigator-design.md`
4. `docs/superpowers/plans/2026-08-26-research-navigator-full-package.md`
5. `docs/requirement-traceability.md`
6. `docs/claim-boundary.md`
7. `delivery/STATUS.json`
8. `delivery/TEST_REPORT.md`
9. `delivery/GAP_LEDGER.csv`

Treat `delivery/STATUS.json` as an assertion to reproduce, not as authority. The approved prompt and actual code/tests are authoritative.

## 1. Required operating stance

- Be adversarial toward unsupported completion claims.
- Do not equate an endpoint, interface, UI placeholder, mock, fixture, or schema with a working feature.
- Do not transform a `NOT_RUN`, `PARTIAL`, or `NOT_IMPLEMENTED` capability into `PASS` without executing its acceptance gate.
- Do not use fixture papers as external-source evidence.
- Do not infer full-text claims from metadata or abstracts.
- Do not describe a gap candidate as proof of novelty.
- Do not bypass paywalls or licensed-source controls.
- Do not weaken user isolation, SSRF protections, upload validation, challenge-state gates, or claim boundaries to make tests easier.
- Preserve V1 behavior while completing V2.

## 2. Establish an independent baseline

Create a new audit run directory:

```bash
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RUN_DIR="codex_audit/runs/$STAMP"
mkdir -p "$RUN_DIR"
```

Record:

```bash
{
  date -u
  pwd
  git rev-parse HEAD
  git status --short
  python --version
  uv --version
  node --version
  npm --version
  docker --version || true
  docker compose version || true
} | tee "$RUN_DIR/environment.txt"
```

Then run, without editing first:

```bash
uv sync --extra dev 2>&1 | tee "$RUN_DIR/uv-sync.log"
pytest -q 2>&1 | tee "$RUN_DIR/pytest-baseline.log"
ruff check apps/api services mcp_servers scripts tests 2>&1 | tee "$RUN_DIR/ruff-baseline.log"
mypy apps/api/research_navigator services mcp_servers 2>&1 | tee "$RUN_DIR/mypy-baseline.log"

cd apps/web
npm ci 2>&1 | tee "../../$RUN_DIR/npm-ci.log"
npm run typecheck 2>&1 | tee "../../$RUN_DIR/frontend-typecheck-baseline.log"
npm test 2>&1 | tee "../../$RUN_DIR/frontend-tests-baseline.log"
npm run build 2>&1 | tee "../../$RUN_DIR/frontend-build-baseline.log"
cd ../..

PYTHONPATH=apps/api:. python scripts/export_openapi.py \
  --output "$RUN_DIR/openapi-baseline.json"
```

If a command fails, preserve the failure. Do not begin by changing tests.

## 3. Create the independent gap ledger

Compare every requirement in `docs/APPROVED_MASTER_PROMPT.txt` with code and runtime evidence. Write `codex_audit/GAP_LEDGER.csv` with columns:

```text
requirement_id,requirement,priority,current_status,evidence_path,acceptance_command,root_cause,planned_action,final_status,final_evidence
```

At minimum audit the following areas separately:

- authentication, logout, session expiry, admin and invitation behavior;
- research profile, project, research question, direction decomposition;
- query formulation, bilingual expansion, saved search, rerun;
- OpenAlex, Crossref, arXiv, Semantic Scholar, Unpaywall;
- licensed-source disabled/not-configured contracts;
- normalization, DOI/arXiv/title deduplication and conflict provenance;
- paper resolve, detail, original links, related/reference/citation behavior;
- favorites, tags, notes, reading status and cross-user isolation;
- PDF rights confirmation, MIME/signature/size checks, SSRF, redirects, path traversal;
- parsing, section detection, chunking, FTS5, dense retrieval, hybrid ranking, citations;
- evidence-level boundaries and missing-field abstention;
- direction similarity and reproduction assessment;
- recommendations and recommendation evidence;
- author disambiguation, CRediT-only contribution display, author cards;
- dataset cards, dataset modality, shape and provenance;
- evidence matrix, gap candidate generation, challenge search and human gate;
- direction map/topic clustering and comparison matrix;
- research plan, plan edits and status;
- AgentRun/ToolCall/PromptVersion audit completeness;
- SQLite job recovery, real handlers, cancellation and duplicate execution;
- MCP SDK v2 stdio behavior and tool schemas;
- React pages, API integration, loading/error/accessibility behavior;
- Docker cold start, restart persistence, backup and restore;
- OpenAPI, Alembic upgrade/downgrade and schema drift;
- security, secrets, logging, authorization and dependency risk;
- PRD/TechDocs/code consistency;
- V1 and V2 release claims.

## 4. P0 verification and correction sequence

Execute in this order. Do not skip to feature expansion while core gates fail.

### P0-A. Dependency and reproducibility locks

1. Generate and commit a valid `uv.lock` with the declared Python floor.
2. Use one frontend package manager; the approved preference is `pnpm`, but retaining npm is acceptable only with an ADR. Commit the corresponding lockfile.
3. Verify clean installation from the lockfiles in a fresh directory or container.
4. Pin Docker image versions intentionally; do not use floating `latest`.
5. Record dependency licenses and known high-severity vulnerabilities.

Acceptance:

```bash
uv sync --frozen --extra dev
uv run pytest -q
cd apps/web && npm ci && npm run typecheck && npm test && npm run build
```

### P0-B. Backend correctness gates

Run and fix without weakening tests:

```bash
pytest -q
ruff check apps/api services mcp_servers scripts tests
mypy apps/api/research_navigator services mcp_servers
python -m compileall -q apps/api services mcp_servers scripts
```

Add tests for every defect before the fix. Inspect especially:

- API route order conflicts such as `/papers/{paper_id}` versus `/papers/resolve`;
- concurrent recommendation refresh and duplicate job execution;
- SQLite worker atomic claim semantics;
- timezone-aware expiry comparisons;
- cascade behavior and FTS orphan cleanup;
- export serialization and cross-user leakage;
- malformed saved-search JSON;
- path containment and symlink behavior;
- external adapter timeout, 429, malformed payload, missing abstract and duplicate identifiers;
- response models that may leak internal paths or raw payloads.

### P0-C. Explicit Alembic history

The supplied initial migration uses metadata bootstrap. Replace it with explicit, reviewable Alembic operations before treating migrations as release-ready.

Required tests:

1. empty database → `alembic upgrade head`;
2. inspect required tables, indexes, foreign keys and FTS creation;
3. `alembic downgrade base` where supported;
4. upgrade again;
5. compare metadata with migration head and report drift;
6. upgrade a V1 fixture database to V2 without losing user data.

Do not make historical migrations depend on future `Base.metadata` state.

### P0-D. Frontend full verification

Install dependencies and run:

```bash
cd apps/web
npm run typecheck
npm test
npm run build
```

Then inspect and test:

- login/register/logout persistence;
- expired token behavior;
- project/profile edit flows;
- search filters, source statuses, rerun and direct paper resolution;
- paper detail, external links, evidence level, citations and missing-field labels;
- PDF rights confirmation, upload errors and deletion;
- favorite/note/tag/reading-state persistence;
- score breakdown and evidence coverage;
- recommendation refresh and explanations;
- gap generated → challenged → confirmed/rejected state transitions;
- plan creation and editing;
- job progress and failure messages;
- workspace export;
- fixture warning visibility;
- responsive layout, keyboard navigation and accessible labels.

The application must not be merely a set of static pages. Use API-backed E2E assertions.

### P0-E. Docker and persistence

Run an actual cold start:

```bash
cp .env.example .env.codex-test
# Use test-only values; do not commit this file.
docker compose --env-file .env.codex-test -f infra/docker-compose.yml build --no-cache
docker compose --env-file .env.codex-test -f infra/docker-compose.yml up -d
```

Acceptance sequence:

1. health endpoints become healthy;
2. register user;
3. create profile/project;
4. search a real open source and a separately marked fixture source;
5. favorite and note a paper;
6. upload a legal test PDF;
7. analyze it;
8. generate/challenge/confirm a gap;
9. create a plan;
10. restart web/api/worker;
11. verify all persisted state remains;
12. `docker compose down`, then `up` again and repeat state verification;
13. verify LAN bind configuration and document the firewall boundary;
14. run backup, destroy test runtime, restore, and verify data.

Record exact container image IDs and logs. Do not call this public SaaS deployment.

### P0-F. MCP SDK v2 runtime

Install the official MCP Python SDK version allowed by `pyproject.toml`. Do not treat `mcp_servers.compat` fallback as runtime proof.

For each server:

- start over stdio;
- enumerate tools and validate names/descriptions/input schemas;
- execute at least one successful tool;
- execute invalid-input, auth-missing, API-unavailable and timeout cases;
- verify user isolation through two tokens;
- verify provenance and explicit unavailable responses;
- verify `delete_local_document` and `export_workspace` call real endpoints;
- verify no tool can fetch arbitrary private-network URLs or bypass paywalls.

Save inspector/transcript output under the run directory.

### P0-G. Live open-source integrations

Run live tests separately from deterministic tests. Use respectful rate limits and identifiable contact values where required.

For OpenAlex, Crossref, arXiv and Semantic Scholar:

- search a stable known paper;
- capture raw response hash without committing excessive raw content;
- normalize to `PaperRecord`;
- verify DOI/arXiv ID, source URL, timestamp and provenance;
- search the same work through two sources and verify conservative deduplication;
- test 429/timeout/malformed response behavior using controlled mocks;
- verify cache or retry policy does not silently return stale fixture data.

Add Unpaywall only when a valid email is configured and terms permit. Licensed sources remain `not_configured` until valid credentials and access terms are available. Never simulate a successful Web of Science or Elsevier integration.

## 5. P1 required functional completion

After all P0 gates are stable, implement missing approved capabilities in isolated, tested increments.

### P1-A. Evidence-grounded LLM provider

Current extraction is deterministic and intentionally limited. Add a provider interface that supports OpenAI-compatible APIs and optional local Ollama while keeping non-LLM features operational without a key.

Requirements:

- Pydantic/JSON Schema output;
- evidence snippets supplied to the model, not unrestricted fabricated context;
- field-level citations;
- citation validator that rejects unsupported fields;
- explicit abstention text `未在当前可访问文本中找到。`;
- model/provider/prompt/version stored in audit records;
- retry and timeout bounds;
- no secret logging;
- deterministic mock provider for tests;
- fixed RAG evaluation fixture with unsupported-field negatives.

Do not let the LLM override `evidence_level`.

### P1-B. Real open-fulltext resolution

Implement a legal access resolver:

- DOI and arXiv resolution;
- Unpaywall/OpenAlex OA locations where configured;
- redirect validation on every hop;
- host/IP revalidation against SSRF;
- content length cap;
- MIME and `%PDF` signature check;
- explicit HTML/login/paywall detection;
- source/license/provenance storage;
- idempotent document hashing;
- deletion rules that never claim remote content was deleted.

### P1-C. References, citations and related work

Implement source-backed references and citations when supported. Keep local content similarity separately labelled. Never conflate:

- bibliographic citation relation;
- source-provided related papers;
- local lexical/vector similarity;
- co-citation or bibliographic coupling.

Every relation must carry relation type, source and retrieval time.

### P1-D. Author and dataset cards

Implement normalized author/source IDs and cautious disambiguation. Do not merge name-only authors. Display individual contribution only when a CRediT statement or equivalent explicit source exists.

Dataset cards must distinguish:

- explicit paper-provided dataset facts;
- source-catalog facts;
- system inference;
- user notes;
- unknown shape/modality/license.

Do not fill unknown dataset shape from model memory.

### P1-E. Direction decomposition and research map

Implement an editable research-direction model with dimensions such as task, input, output, data, supervision, horizon, method, application, constraints and evaluation. Generate bilingual search expressions with exact provenance and version.

Topic mapping must show corpus size, algorithm, parameters and unstable-cluster warnings. A sparse keyword cell alone cannot become a gap claim.

### P1-F. Comparison matrix and recommendation evaluation

Complete API-backed paper comparison and recommendation categories:

- entry survey;
- classic/foundational;
- task-defining;
- method;
- high-relevance recent;
- counter-route;
- reproduction candidate.

Recommendation reasons must expose components and evidence. Do not call a venue “top” without a versioned, auditable venue source. Create offline ranking fixtures and expert-review protocol; do not fabricate NDCG or user gains.

### P1-G. Complete audit schema

The master prompt requests entities beyond the current minimal schema. Decide explicitly whether to add or rationally replace:

- invitations;
- research_questions;
- search_queries;
- source_requests;
- authors and paper_authors;
- venues;
- dataset_cards and author_cards;
- prompt_versions;
- data_source_configs;
- tool_calls;
- audit_logs;
- app_settings.

For every omitted table, document the normalized replacement and prove no required behavior is lost. Do not add empty tables solely to satisfy a list.

## 6. P2 robustness and evaluation

Implement only after P0/P1 stability:

- scheduled incremental searches with duplicate-safe cursors;
- source quota/rate-limit observability;
- concept drift in research profiles and recommendation refresh;
- multi-user LAN load test with SQLite contention metrics;
- retrieval evaluation: hit rate, citation precision/coverage, faithfulness, structured extraction accuracy, abstention accuracy, parser failure rate;
- recommendation evaluation: Precision@10, Recall@K, NDCG@10 on a documented relevance set;
- expert gap review: worth-investigating rate, challenge-overturn rate, evidence coverage, human edit rate;
- structured feedback capture without calling an offline form an online learning loop;
- backup compatibility and upgrade rollback drills.

Never optimize or report quality on a hidden test set that was used for prompt/rule selection.

## 7. Security audit checklist

Run and document:

- dependency vulnerability scan;
- secret scan including history if permitted;
- SQL injection attempts;
- cross-user IDOR tests on every private endpoint;
- bearer token expiry/revocation tests;
- login brute-force/rate-limit decision;
- CORS boundary;
- PDF size/MIME/signature/filename/path/symlink tests;
- SSRF tests for localhost, RFC1918, link-local, IPv6, redirects, DNS rebinding assumptions;
- ZIP path traversal on restore;
- log redaction for tokens/keys/query payloads;
- formula/CSV injection in exports if CSV is introduced;
- Docker non-root user and writable-volume ownership;
- Nginx security headers and upload cap;
- SQLite backup consistency while API/worker are active.

Do not claim a penetration test unless a real scoped test was performed.

## 8. Required test architecture

Keep these suites distinct:

```text
tests/unit/          deterministic logic
tests/integration/   local database/API/worker/MCP-client integration
tests/contract/      artifact/OpenAPI/schema contracts
tests/live/          opt-in real open API calls
apps/web/src/**/*.test.*
apps/web/tests/e2e/
tests/rag_eval/
tests/security/
```

Live and licensed tests must be opt-in and must not make default CI flaky. Skips must state the missing credential/configuration.

## 9. Commit and review protocol

Use small commits such as:

```text
chore: lock reproducible dependencies
fix: atomically claim sqlite jobs
test: add cross-user document deletion denial
feat: add citation-validated llm provider
feat: resolve legal open full text
feat: persist source-backed author identities
feat: add editable direction decomposition
fix: make docker restart persistence pass
chore: verify mcp stdio contracts
```

After every major feature, perform two reviews:

1. specification review — does it satisfy the approved requirement without expanding the claim?
2. code-quality review — types, error handling, isolation, security, tests and maintainability.

Do not combine unrelated mass refactors with feature completion.

## 10. Final verification matrix

Before completion, run and save exact output for:

```bash
uv sync --frozen --extra dev
pytest -q
pytest -q tests/security tests/rag_eval
ruff check apps/api services mcp_servers scripts tests
mypy apps/api/research_navigator services mcp_servers
python -m compileall -q apps/api services mcp_servers scripts

PYTHONPATH=apps/api:. alembic upgrade head
PYTHONPATH=apps/api:. python scripts/export_openapi.py --output codex_audit/OPENAPI.json

cd apps/web
npm ci
npm run typecheck
npm test
npm run build
npm run test:e2e
cd ../..

docker compose -f infra/docker-compose.yml config
docker compose -f infra/docker-compose.yml build --no-cache
# Execute the persistence scenario described above.
```

Also execute MCP stdio and live-source suites when prerequisites are available.

## 11. Required final artifacts

Create or update:

- `codex_audit/FINAL_STATUS.json`
- `codex_audit/TEST_REPORT.md`
- `codex_audit/GAP_LEDGER.csv`
- `codex_audit/CHANGE_LEDGER.md`
- `codex_audit/SECURITY_REPORT.md`
- `codex_audit/LIVE_SOURCE_REPORT.md`
- `codex_audit/MCP_REPORT.md`
- `codex_audit/DOCKER_PERSISTENCE_REPORT.md`
- `delivery/OPENAPI.json`
- `delivery/STATUS.json`
- `delivery/TEST_REPORT.md`
- `delivery/FILE_MANIFEST.json`
- `delivery/SHA256SUMS.txt`
- `docs/requirement-traceability.md`
- `docs/claim-boundary.md`
- release notes and CHANGELOG.

`FINAL_STATUS.json` must contain at least:

```json
{
  "audited_commit": "...",
  "audit_time_utc": "...",
  "overall_status": "PASS|PARTIAL|FAIL",
  "backend": {},
  "frontend": {},
  "docker": {},
  "mcp": {},
  "live_sources": {},
  "security": {},
  "migrations": {},
  "known_gaps": [],
  "claim_boundary": []
}
```

## 12. Stop conditions

Stop and report rather than inventing success when:

- required licensed credentials are unavailable;
- a source forbids the intended access method;
- a test exposes a fundamental product-spec conflict;
- Docker or browser infrastructure is unavailable;
- a dependency cannot be legally or reproducibly installed;
- full-text evidence is unavailable;
- expert evaluation has not occurred.

Partial completion with precise evidence is preferred over a false final release.

## 13. Final response format

Return:

1. **Audit conclusion** — overall PASS/PARTIAL/FAIL and why.
2. **Baseline defects** — issues found before edits.
3. **Implemented corrections** — grouped by commit.
4. **Verified matrix** — commands, counts and statuses.
5. **Unresolved items** — blocker, risk and next legal action.
6. **Claim boundary** — what the product and résumé may and may not say.
7. **Run instructions** — exact local/Docker/MCP commands.
8. **Artifact paths** — all audit files.

Do not state “complete”, “production ready”, “online”, “MCP integrated”, “all tests passed”, or “research gap discovered” unless the corresponding evidence gate passed in the audited environment.
