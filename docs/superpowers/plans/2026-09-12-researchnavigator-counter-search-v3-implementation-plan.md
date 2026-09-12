# ResearchNavigator Counter-search V3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Papers.cool as a safe supplementary discovery source and refactor research-opportunity challenge search into a multi-source counter-search that includes closed-access papers through metadata/abstract evidence without weakening scientific claim boundaries.

**Architecture:** Reuse the existing `ScholarlyAdapter`/`FederatedSearchService`, `PaperRecord`/`PaperSource`, and gap challenge persistence seams. Separate normal-search ranking from counter-search falsification-risk ranking, classify evidence access independently from relevance, and preserve per-source status/provenance. Do not create `0010` unless schema-impact review proves the existing `0009` schema cannot safely persist required durable state.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, Pydantic, httpx, pytest, React 19, TypeScript, Ant Design 6, Vitest, Playwright, Turso/libSQL, Alembic.

**Spec:** `docs/superpowers/specs/2026-09-12-researchnavigator-counter-search-v3-design.md`

## Global Constraints

- Implementation base commit: `5ad162bbf04b41480bc7e9a1d46f43dfb80c3379`.
- Current production schema: `0009`.
- R2.1 Production health/auth/OpenAlex/Turso/topic-navigation/search-restore/library-layout/Chinese-reading-status/unknown-vs-zero/exploration-plan/loading/duplicate-submit boundaries are accepted and must not regress.
- Translation remains `BLOCKED_CONFIG`; V3 must not silently claim translation availability.
- No paywall bypass, institutional-login automation, robots bypass, anti-bot bypass, or unsupported Papers.cool scraper.
- Closed-access work may participate using legally accessible metadata/abstracts; lack of full text never means “not researched”.
- Metadata-only evidence cannot support hidden method/experiment/limitation/Future Work claims.
- Abstract evidence supports only explicit abstract claims.
- No global-novelty claims.
- User-owned state remains scoped by `user_id`.
- Use RED → GREEN → REFACTOR for every behavior change.
- Stop at local V3 checkpoint. Do not modify Production Turso or Vercel without separate authorization.

---

### Task 1: Establish isolated V3 baseline and preserve R2.1 acceptance

**Files:**
- Read: `AGENTS.md`
- Read: `docs/APPROVED_MASTER_PROMPT.txt`
- Read: `docs/superpowers/specs/2026-09-12-researchnavigator-counter-search-v3-design.md`
- Create: `codex_audit/runs/20260912_counter_search_v3/BASELINE.md`
- Create: `codex_audit/runs/20260912_counter_search_v3/TEST_REPORT.md`
- Create: `codex_audit/runs/20260912_counter_search_v3/SCHEMA_IMPACT.md`

**Interfaces:**
- Consumes: accepted R2.1 commit `5ad162bb...`.
- Produces: clean isolated V3 worktree/branch and recorded baseline gates.

- [ ] **Step 1: Create or verify isolated worktree**

Use platform-native worktree support when available; otherwise create branch `feature/rn-counter-search-v3-20260912` from exactly `5ad162bbf04b41480bc7e9a1d46f43dfb80c3379`.

- [ ] **Step 2: Record identity and toolchain**

Run:

```powershell
git rev-parse HEAD
git branch --show-current
git status --short
python --version
node --version
pnpm --version
```

Expected HEAD: `5ad162bbf04b41480bc7e9a1d46f43dfb80c3379`.

- [ ] **Step 3: Run backend baseline**

```powershell
pytest -q
ruff check apps/api services mcp_servers scripts tests
mypy apps/api/research_navigator services mcp_servers
```

Record exact baseline debt separately from V3 regressions.

- [ ] **Step 4: Run frontend baseline**

```powershell
cd apps/web
pnpm run typecheck
pnpm test
pnpm run build
cd ../..
```

- [ ] **Step 5: Commit audit setup only if repository policy requires tracked run evidence**

Do not mix audit setup with product code.

---

### Task 2: Perform Papers.cool source-access contract spike before adapter implementation

**Files:**
- Create: `docs/source-contracts/papers-cool.md`
- Create: `tests/contract/test_papers_cool_access_contract.py`

**Interfaces:**
- Produces: explicit status `SUPPORTED_PROGRAMMATIC_ACCESS` or `BLOCKED_SOURCE_ACCESS_CONTRACT`.
- No production adapter may exist unless status is `SUPPORTED_PROGRAMMATIC_ACCESS`.

- [ ] **Step 1: Write contract test that requires an explicit access decision**

Create a test that reads `docs/source-contracts/papers-cool.md` and asserts it contains exactly one machine-readable line:

```text
access_status: SUPPORTED_PROGRAMMATIC_ACCESS
```

or

```text
access_status: BLOCKED_SOURCE_ACCESS_CONTRACT
```

The first RED state is absence of the document.

- [ ] **Step 2: Verify RED**

```powershell
pytest tests/contract/test_papers_cool_access_contract.py -q
```

Expected: FAIL because contract file is absent.

- [ ] **Step 3: Investigate Papers.cool only through publicly documented, terms-compliant access paths**

Document:

- public endpoint/mechanism actually observed;
- whether automated search is supported;
- rate/usage constraints if documented;
- fields available: title/authors/year/venue/DOI/arXiv/abstract/source URL;
- whether direct HTML crawling would be unsupported;
- one reproducible safe request if supported.

Do not bypass anti-bot controls.

- [ ] **Step 4: Write the source contract**

If safe programmatic access cannot be proven, write:

```text
access_status: BLOCKED_SOURCE_ACCESS_CONTRACT
```

and explain that the V3 architecture continues without a production Papers.cool adapter.

- [ ] **Step 5: Verify contract PASS**

```powershell
pytest tests/contract/test_papers_cool_access_contract.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add docs/source-contracts/papers-cool.md tests/contract/test_papers_cool_access_contract.py
git commit -m "docs: establish Papers.cool source access contract"
```

---

### Task 3: Extend scholarly contracts for Papers.cool and evidence-access status

**Files:**
- Modify: `apps/api/research_navigator/scholarly/base.py`
- Modify: `apps/api/research_navigator/config.py`
- Modify: `apps/api/research_navigator/scholarly/service.py`
- Test: `tests/unit/test_counter_search_v3_contracts.py`

**Interfaces:**
- Produces `SearchRequest.source_queries` support for `papers_cool`.
- Produces source status support for `timeout` and `blocked_access_contract`.
- Produces `PaperRecord.access_level` with values `metadata_only`, `abstract_available`, `open_fulltext`, `publisher_fulltext_unavailable`, `user_uploaded_fulltext`, `publisher_authorized_fulltext`.

- [ ] **Step 1: Write failing contract tests**

Create tests asserting:

```python
SearchRequest(query="x", source_queries={"papers_cool": "x"})
```

is valid; `SourceStatus(status="blocked_access_contract")` is valid; and `PaperRecord(title="x", access_level="metadata_only")` is valid.

- [ ] **Step 2: Verify RED**

```powershell
pytest tests/unit/test_counter_search_v3_contracts.py -q
```

- [ ] **Step 3: Implement minimal contracts**

Add `papers_cool` to allowed source-query keys. Extend `SourceStatus.status` literals. Add optional/defaulted `access_level` to `PaperRecord` so legacy adapters remain source-compatible.

Add config fields:

```text
RN_ENABLE_PAPERS_COOL
RN_PAPERS_COOL_BASE_URL
```

Default source enablement must be `false` until the source-access contract is supported.

- [ ] **Step 4: Verify GREEN and regression**

```powershell
pytest tests/unit/test_counter_search_v3_contracts.py -q
pytest -q
mypy apps/api/research_navigator
```

- [ ] **Step 5: Commit**

```powershell
git add apps/api/research_navigator/scholarly/base.py apps/api/research_navigator/config.py apps/api/research_navigator/scholarly/service.py tests/unit/test_counter_search_v3_contracts.py
git commit -m "feat: extend scholarly contracts for counter search"
```

---

### Task 4: Implement Papers.cool adapter only when access contract is supported

**Files:**
- Create when supported: `apps/api/research_navigator/scholarly/papers_cool.py`
- Modify when supported: `apps/api/research_navigator/scholarly/service.py`
- Test: `tests/unit/test_papers_cool_adapter.py`
- Test: `tests/integration/test_papers_cool_live.py`

**Interfaces:**
- Consumes: Task 2 access contract.
- Produces: `PapersCoolAdapter(ScholarlyAdapter)` named `papers_cool`.

- [ ] **Step 1: Branch on source-contract result**

If contract is `BLOCKED_SOURCE_ACCESS_CONTRACT`, do not create a network adapter. Configure source-status behavior to report `blocked_access_contract` when requested, and proceed to Task 5.

If contract is `SUPPORTED_PROGRAMMATIC_ACCESS`, continue.

- [ ] **Step 2: Write failing adapter mapping tests**

Use fixture HTTP transport, not live network, to assert one supported response maps into `PaperRecord` with:

- source provenance `papers_cool`;
- stable source ID;
- title/authors/year/venue;
- DOI/arXiv where exposed;
- abstract only if source legally exposes it;
- source URL;
- correct `access_level`.

- [ ] **Step 3: Verify RED**

```powershell
pytest tests/unit/test_papers_cool_adapter.py -q
```

- [ ] **Step 4: Implement adapter using only the documented source contract**

Use bounded timeout, a descriptive user agent where permitted, no redirect bypass, no anti-bot workaround, and no HTML scraping unless explicitly supported by the source contract.

- [ ] **Step 5: Verify unit GREEN**

```powershell
pytest tests/unit/test_papers_cool_adapter.py -q
```

- [ ] **Step 6: Run one live source smoke**

```powershell
pytest tests/integration/test_papers_cool_live.py -q -m live
```

PASS requires real returned scholarly records and visible provenance. If the source blocks automated access, classify `BLOCKED_SOURCE_ACCESS_CONTRACT`; do not weaken the test or add scraping bypasses.

- [ ] **Step 7: Commit supported adapter or blocked-status seam**

Use commit message:

```text
feat: add safe Papers.cool discovery source
```

or, if blocked:

```text
feat: expose Papers.cool access-contract status
```

---

### Task 5: Improve multi-source identity resolution without provenance loss

**Files:**
- Modify: `apps/api/research_navigator/scholarly/normalize.py`
- Modify: `apps/api/research_navigator/scholarly/repository.py`
- Test: `tests/unit/test_multisource_identity_resolution.py`

**Interfaces:**
- Consumes `PaperRecord.source_provenance`, DOI/arXiv/title metadata.
- Produces conservative deduplicated records retaining all source provenance.

- [ ] **Step 1: Write failing tests for duplicate cross-source records**

Test cases:

1. same DOI from OpenAlex + Papers.cool => one record, two provenances;
2. same arXiv ID from arXiv + Papers.cool => one record, two provenances;
3. same normalized title/year/first-author => merge only when consistent;
4. same title but conflicting year/author => remain separate;
5. longer verified abstract may replace shorter abstract without losing old source provenance.

- [ ] **Step 2: Verify RED**

```powershell
pytest tests/unit/test_multisource_identity_resolution.py -q
```

- [ ] **Step 3: Implement minimal conservative merge changes**

Do not introduce fuzzy merging that can silently combine ambiguous papers.

- [ ] **Step 4: Verify GREEN and repository persistence**

```powershell
pytest tests/unit/test_multisource_identity_resolution.py -q
pytest tests/integration -q
```

- [ ] **Step 5: Commit**

```powershell
git add apps/api/research_navigator/scholarly/normalize.py apps/api/research_navigator/scholarly/repository.py tests/unit/test_multisource_identity_resolution.py
git commit -m "fix: preserve provenance in multi-source paper identity"
```

---

### Task 6: Add counter-search access classification and falsification-risk ranking

**Files:**
- Create: `apps/api/research_navigator/gaps/counter_search.py`
- Modify: `apps/api/research_navigator/gaps/service.py`
- Test: `tests/unit/test_counter_search_classification.py`

**Interfaces:**
- Produces `CounterEvidenceAssessment` with fields:

```text
paper_id
classification
access_level
risk_score
rationale
supported_by_abstract
unresolved_checks
```

- Classification values: `verified_counterexample`, `high_risk_potential_counterexample`, `related_work_needs_verification`, `metadata_only_lead`, `background_low_risk`.

- [ ] **Step 1: Write failing classification tests**

Include:

- metadata-only paid paper => `metadata_only_lead` and never verified;
- public abstract explicitly covering candidate question => at least high-risk and eligible for verified only when the abstract itself materially establishes equivalence;
- closed full text with public abstract remains visible;
- no abstract/full text never becomes evidence of non-overlap;
- open-access status does not boost falsification relevance by itself.

- [ ] **Step 2: Verify RED**

```powershell
pytest tests/unit/test_counter_search_classification.py -q
```

- [ ] **Step 3: Implement deterministic bounded classifier**

Use candidate scope/question + title/abstract/metadata. Keep rationale explicit. Do not infer hidden full-text facts.

- [ ] **Step 4: Add counter-search ranking**

Sort primarily by `risk_score`, then evidence quality/source diversity/recency where applicable. Do not reuse normal-search `source_score` as the sole ranking objective.

- [ ] **Step 5: Verify GREEN**

```powershell
pytest tests/unit/test_counter_search_classification.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add apps/api/research_navigator/gaps/counter_search.py apps/api/research_navigator/gaps/service.py tests/unit/test_counter_search_classification.py
git commit -m "feat: rank counter search by falsification risk"
```

---

### Task 7: Refactor challenge search into broad multi-source counter-search

**Files:**
- Modify: `apps/api/research_navigator/gaps/service.py`
- Modify: `apps/api/research_navigator/routes/gaps.py`
- Modify: `apps/api/research_navigator/schemas/gaps.py`
- Test: `tests/integration/test_multisource_counter_search.py`

**Interfaces:**
- Consumes `FederatedSearchService.search()` and Task 6 classifier.
- Persists source coverage into existing `GapCandidate.data_sources_json`/`coverage_json`, counter records into `counter_evidence_json`, and paper-level evidence roles in `GapEvidence`.

- [ ] **Step 1: Write failing integration tests**

Assert:

- counter-search invokes all enabled/configured discovery sources;
- one source timeout does not erase other-source results;
- per-source status is preserved;
- a duplicate work from two sources appears once with both provenances;
- metadata-only and abstract-available paid papers remain in counter results;
- source failure prevents a false "complete coverage" state;
- fixture records never become scientific counter-evidence.

- [ ] **Step 2: Verify RED**

```powershell
pytest tests/integration/test_multisource_counter_search.py -q
```

- [ ] **Step 3: Implement broader counter-search request policy**

Normal search keeps user-selected sources. Counter-search uses all enabled/configured scholarly sources by default, including Papers.cool only when its access contract is supported.

- [ ] **Step 4: Persist classification and coverage using existing schema**

Use JSON payloads already available on `GapCandidate` plus `GapEvidence` rows. Include source name, source query, classification, access level, rationale, and unresolved checks.

- [ ] **Step 5: Verify GREEN and claim boundaries**

```powershell
pytest tests/integration/test_multisource_counter_search.py -q
pytest tests/contract -q
pytest tests/security -q
```

- [ ] **Step 6: Commit**

```powershell
git add apps/api/research_navigator/gaps/service.py apps/api/research_navigator/routes/gaps.py apps/api/research_navigator/schemas/gaps.py tests/integration/test_multisource_counter_search.py
git commit -m "feat: broaden research opportunity counter search"
```

---

### Task 8: Add Papers.cool to ordinary search UI and expose access/source evidence separately

**Files:**
- Modify: `apps/web/src/pages/SearchPage.tsx`
- Modify: `apps/web/src/components/SearchSourceEvidence.tsx`
- Modify: `apps/web/src/types/domain.ts`
- Test: `apps/web/src/pages/SearchPage.counterSearchV3.test.tsx`

**Interfaces:**
- Displays `papers_cool` only when backend capability/source status exposes it.
- Keeps OA/access status separate from scholarly relevance.

- [ ] **Step 1: Write failing frontend tests**

Assert:

- Papers.cool source label renders when available;
- source query editor uses `papers_cool` key;
- `blocked_access_contract` is rendered as a bounded Chinese explanation;
- a paid paper with public abstract is not hidden when `open_access_only=false`;
- `open_access_only=true` remains an explicit user filter and is not applied to counter-search automatically.

- [ ] **Step 2: Verify RED**

```powershell
cd apps/web
pnpm test -- SearchPage.counterSearchV3.test.tsx
```

- [ ] **Step 3: Implement UI**

Use Chinese source/status copy. Do not imply Papers.cool is authoritative or that paid papers are fully read.

- [ ] **Step 4: Verify GREEN**

```powershell
pnpm test -- SearchPage.counterSearchV3.test.tsx
pnpm run typecheck
cd ../..
```

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/pages/SearchPage.tsx apps/web/src/components/SearchSourceEvidence.tsx apps/web/src/types/domain.ts apps/web/src/pages/SearchPage.counterSearchV3.test.tsx
git commit -m "feat: expose Papers.cool in paper discovery"
```

---

### Task 9: Redesign counter-search UI around risk, source coverage, and unresolved evidence

**Files:**
- Modify: `apps/web/src/pages/GapsPage.tsx`
- Modify: `apps/web/src/types/domain.ts`
- Modify: `apps/web/src/lib/researchDisplay.ts`
- Test: `apps/web/src/pages/GapsPage.counterSearchV3.test.tsx`

**Interfaces:**
- Displays counter-evidence class, access level, source provenance, and unresolved checks.
- Keeps existing loading and duplicate-submit protections.

- [ ] **Step 1: Write failing tests**

Assert UI groups/counts:

- 已核实反例;
- 高风险潜在反例;
- 待核实相关工作;
- 仅元数据线索;
- 低风险背景.

Assert a paid paper with abstract shows "摘要可核实 / 正文暂不可访问" rather than disappearing. Assert source coverage/failures are visible. Assert no copy says "无人研究" or equivalent.

- [ ] **Step 2: Verify RED**

```powershell
cd apps/web
pnpm test -- GapsPage.counterSearchV3.test.tsx
```

- [ ] **Step 3: Implement summary and ranked list**

Show highest falsification risk first and provide safe actions: official record, find OA version where supported, mark for verification.

- [ ] **Step 4: Preserve R2.1 interaction behavior**

Loading must remain immediate; repeated submit remains disabled/guarded; exploration-plan paths remain usable.

- [ ] **Step 5: Verify GREEN**

```powershell
pnpm test -- GapsPage.counterSearchV3.test.tsx
pnpm run typecheck
cd ../..
```

- [ ] **Step 6: Commit**

```powershell
git add apps/web/src/pages/GapsPage.tsx apps/web/src/types/domain.ts apps/web/src/lib/researchDisplay.ts apps/web/src/pages/GapsPage.counterSearchV3.test.tsx
git commit -m "feat: explain counter evidence risk and coverage"
```

---

### Task 10: Schema-impact review — default decision is no `0010`

**Files:**
- Modify: `codex_audit/runs/20260912_counter_search_v3/SCHEMA_IMPACT.md`
- Test: `tests/contract/test_counter_search_schema_impact.py`

**Interfaces:**
- Produces exact decision `NO_MIGRATION_REQUIRED` or `MIGRATION_REQUIRED` with field-by-field justification.

- [ ] **Step 1: Write schema-impact contract test**

Test requires one explicit line in the report:

```text
schema_decision: NO_MIGRATION_REQUIRED
```

or

```text
schema_decision: MIGRATION_REQUIRED
```

- [ ] **Step 2: Map required durable data to current schema**

Verify current `0009` can represent:

- discovered paper metadata;
- multi-source provenance through `PaperSource`;
- counter evidence in `GapCandidate.counter_evidence_json`;
- source list/coverage in `data_sources_json` and `coverage_json`;
- per-paper roles/rationale/source query in `GapEvidence`;
- workflow snapshot in `AgentRun`.

- [ ] **Step 3: Prefer `NO_MIGRATION_REQUIRED` when all contracts are safely representable**

Do not add `0010` just for normalized convenience.

- [ ] **Step 4: If and only if essential durable semantics cannot be represented safely, STOP before creating migration**

Return `MIGRATION_REQUIRED` with the exact missing durable contract. Do not create `0010` in this task without fresh user authorization.

- [ ] **Step 5: Verify schema-impact test**

```powershell
pytest tests/contract/test_counter_search_schema_impact.py -q
```

- [ ] **Step 6: Commit report**

```powershell
git add codex_audit/runs/20260912_counter_search_v3/SCHEMA_IMPACT.md tests/contract/test_counter_search_schema_impact.py
git commit -m "docs: record counter-search V3 schema impact"
```

---

### Task 11: Full local regression and V3 browser acceptance

**Files:**
- Modify: `codex_audit/runs/20260912_counter_search_v3/TEST_REPORT.md`
- Create: `apps/web/tests/e2e/counter-search-v3.spec.ts`

**Interfaces:**
- Produces local acceptance evidence only; no Production deployment.

- [ ] **Step 1: Run full backend gates**

```powershell
pytest -q
ruff check apps/api services mcp_servers scripts tests
mypy apps/api/research_navigator services mcp_servers
```

Historical Ruff debt may be classified only by exact comparison with base `5ad162bb...`; no new changed-file violations are allowed.

- [ ] **Step 2: Run full frontend gates**

```powershell
cd apps/web
pnpm run typecheck
pnpm test
pnpm run build
cd ../..
```

- [ ] **Step 3: Add E2E scenarios**

Scenario A: normal search exposes Papers.cool when safely available.

Scenario B: same work returned by two sources displays once with multiple provenances.

Scenario C: counter-search retains a paid/closed-access paper with metadata/abstract and classifies it without pretending to read full text.

Scenario D: one source fails while other results remain; UI displays partial coverage.

Scenario E: no directly verified counterexample results in bounded language, not a novelty claim.

Scenario F: existing R2.1 global back, loading, duplicate-submit guard, exploration plan, reading status, and unknown-vs-zero behavior remain intact.

- [ ] **Step 4: Run Playwright if local services/browser are available**

```powershell
cd apps/web
pnpm run test:e2e:playwright
cd ../..
```

If environment blocks browser startup, classify `BLOCKED_ENVIRONMENT`; a real executed product failure is not an environment block.

- [ ] **Step 5: Commit E2E and report**

```powershell
git add apps/web/tests/e2e/counter-search-v3.spec.ts codex_audit/runs/20260912_counter_search_v3/TEST_REPORT.md
git commit -m "test: verify multi-source counter-search V3"
```

---

### Task 12: Create local V3 checkpoint and stop before Production

**Files:**
- Create: `codex_audit/runs/20260912_counter_search_v3/FINAL_STATUS.json`
- Modify: `codex_audit/runs/20260912_counter_search_v3/TEST_REPORT.md`

**Interfaces:**
- Produces local checkpoint commit and one of the final local states below.

- [ ] **Step 1: Verify no secrets or runtime databases are staged**

```powershell
git status --short
git diff --check
```

- [ ] **Step 2: Verify Production untouched**

Receipt must state:

```text
production_turso_accessed=false
production_vercel_modified=false
production_deployed=false
production_secret_accessed=false
```

- [ ] **Step 3: Record Papers.cool state**

One of:

```text
papers_cool_status=PASS_LIVE_TERMS_COMPLIANT
```

or

```text
papers_cool_status=BLOCKED_SOURCE_ACCESS_CONTRACT
```

Do not use `PASS` without a real live smoke.

- [ ] **Step 4: Record schema decision**

Preferred:

```text
schema_decision=NO_MIGRATION_REQUIRED
```

If `MIGRATION_REQUIRED`, stop before writing `0010`.

- [ ] **Step 5: Create checkpoint commit**

```powershell
git add <explicit V3 source/test/audit files>
git commit -m "feat: prepare ResearchNavigator counter-search V3 checkpoint"
git rev-parse HEAD
```

Never use `git add .`.

- [ ] **Step 6: Stop**

Do not update `deploy/researchnavigator-beta`, Turso, or Vercel.

Accepted local terminal states:

```text
RN_COUNTER_SEARCH_V3_LOCAL_CHECKPOINT_PASS
```

or

```text
RN_COUNTER_SEARCH_V3_LOCAL_CHECKPOINT_PASS_WITH_PAPERS_COOL_BLOCKED
```

or

```text
RN_COUNTER_SEARCH_V3_SCHEMA_AUTHORIZATION_REQUIRED
```

or

```text
RN_COUNTER_SEARCH_V3_BLOCKED
```

## Required Final Receipt

```text
task_status:
execution_id:

base_commit:
feature_branch:
checkpoint_commit:

r21_regression_status:
translation_status:

papers_cool_access_contract:
papers_cool_adapter_status:
papers_cool_live_smoke:

ordinary_search_sources:
counter_search_sources:
source_failure_visibility:

multisource_dedup:
provenance_preserved:

metadata_only_paid_paper_behavior:
abstract_available_paid_paper_behavior:
fulltext_unavailable_behavior:

verified_counterexample_behavior:
high_risk_counterexample_behavior:
metadata_only_lead_behavior:

counter_search_ranking:
normal_search_ranking_unchanged:

schema_decision:
migration_created:
production_schema_touched:

pytest_full:
mypy:
changed_file_ruff:
frontend_typecheck:
frontend_vitest:
frontend_build:
playwright_local:

claim_boundary:
account_isolation:
secret_exposure:

production_turso_accessed:
production_vercel_modified:
production_deployed:

first_failure_if_any:
remaining_non_blocking_items:
next_required_action:
```
