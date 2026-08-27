# ResearchNavigator 2.2.0 Research Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add provenance-aware author cards, dataset cards, deterministic direction clustering, and real-expert evaluation infrastructure without inventing missing scholarly facts.

**Architecture:** Build independent services and additive APIs over the shared paper/analysis records. Cards are source-backed and abstain when identity is ambiguous. Clustering is deterministic and versioned. Evaluation infrastructure separates real expert ratings from simulations and never auto-upgrades outcome validation.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, SQLite, React, TypeScript, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-28-researchnavigator-2.2.0-evidence-platform-design.md`

## Global Constraints

- Name-only authors are never merged.
- No per-author contribution is inferred without source-backed CRediT evidence.
- Dataset fields not present in accessible evidence remain unknown.
- Clusters are literature organization results, not objective field taxonomies.
- Simulated or developer ratings cannot set expert validation to PASS.

---

### Task 1: Author identity and card service

**Files:**
- Create: `apps/api/research_navigator/authors/__init__.py`
- Create: `apps/api/research_navigator/authors/service.py`
- Create: `apps/api/research_navigator/schemas/authors.py`
- Create: `apps/api/research_navigator/routes/authors.py`
- Modify: `apps/api/research_navigator/main.py`
- Test: `tests/unit/test_author_identity.py`
- Test: `tests/integration/test_author_cards.py`

**Interfaces:**
- Produces `refresh_author_cards(session, paper, source_records) -> list[Author]`.
- `GET /api/papers/{paper_id}/authors` and `GET /api/authors/{author_id}`.

- [ ] Write RED tests proving ORCID/source-ID merge and name-only non-merge.
- [ ] Implement canonical identity keys, provenance, and unresolved status.
- [ ] Write API RED tests for source-backed fields and cross-user access to user-owned enrichment details.
- [ ] Implement routes and commit `feat(authors): add provenance-aware author cards`.

### Task 2: Dataset mention and card service

**Files:**
- Create: `apps/api/research_navigator/datasets/__init__.py`
- Create: `apps/api/research_navigator/datasets/service.py`
- Create: `apps/api/research_navigator/schemas/datasets.py`
- Create: `apps/api/research_navigator/routes/datasets.py`
- Modify: `apps/api/research_navigator/main.py`
- Test: `tests/unit/test_dataset_extraction.py`
- Test: `tests/integration/test_dataset_cards.py`

**Interfaces:**
- Produces `refresh_dataset_cards(session, analysis_record) -> list[PaperDatasetMention]`.
- `GET /api/papers/{paper_id}/datasets` and `GET /api/datasets/{dataset_id}`.

- [ ] Write RED tests for abstract name-only, full-text split evidence, absent license, and citation binding.
- [ ] Implement conservative extraction and identity status.
- [ ] Implement routes and commit `feat(datasets): add evidence-bounded dataset cards`.

### Task 3: Deterministic direction clustering

**Files:**
- Create: `apps/api/research_navigator/clustering/__init__.py`
- Create: `apps/api/research_navigator/clustering/service.py`
- Create: `apps/api/research_navigator/schemas/clustering.py`
- Create: `apps/api/research_navigator/routes/clustering.py`
- Modify: `apps/api/research_navigator/main.py`
- Test: `tests/unit/test_direction_clustering.py`
- Test: `tests/integration/test_direction_clusters.py`

**Interfaces:**
- Produces `run_direction_clustering(session, user_id, project_id, paper_ids, threshold) -> DirectionClusterRun`.
- `POST /api/projects/{project_id}/direction-clusters` and `GET /api/direction-clusters/{run_id}`.

- [ ] Write RED tests for deterministic membership/order/input hash, evidence distribution, threshold behavior, and unclustered papers.
- [ ] Implement local hashing vectors, cosine graph, connected components, and label terms.
- [ ] Add cross-user denial and commit `feat(map): add deterministic direction clustering`.

### Task 4: Real-expert evaluation infrastructure

**Files:**
- Create: `apps/api/research_navigator/evaluations/__init__.py`
- Create: `apps/api/research_navigator/evaluations/service.py`
- Create: `apps/api/research_navigator/schemas/evaluations.py`
- Create: `apps/api/research_navigator/routes/evaluations.py`
- Modify: `apps/api/research_navigator/main.py`
- Test: `tests/integration/test_expert_evaluations.py`

**Interfaces:**
- Creates frozen studies/tasks, blinded assignments, expert ratings, and aggregate results.
- `POST /api/evaluations/studies`, assignment/rating endpoints, and result endpoint.

- [ ] Write RED tests for frozen version hashes, blinded randomized order, one rating per assignment, timing, aggregation, and inter-rater agreement.
- [ ] Write RED test that simulated/developer ratings cannot set `expert_outcome_validation=verified`.
- [ ] Implement service/routes and commit `feat(evals): add real-expert study workflow`.

### Task 5: Frontend paper intelligence and evaluation pages

**Files:**
- Modify: `apps/web/src/types/domain.ts`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/pages/PaperPage.tsx`
- Create: `apps/web/src/pages/DirectionMapPage.tsx`
- Create: `apps/web/src/pages/EvaluationsPage.tsx`
- Modify: `apps/web/src/app/App.tsx`
- Test: `apps/web/src/pages/PaperIntelligence.test.tsx`
- Test: `apps/web/src/pages/DirectionMapPage.test.tsx`

**Interfaces:**
- Paper page renders author/dataset cards with provenance and unknown/unresolved states.
- Direction map renders cluster terms, members, evidence distribution, and taxonomy disclaimer.
- Evaluation page distinguishes awaiting-real-experts from completed real studies.

- [ ] Write failing component tests for abstention/disclaimer/status semantics.
- [ ] Implement API client/types/pages without blocking existing paper rendering when endpoints are empty.
- [ ] Run typecheck/unit/build and commit `feat(web): expose research map and evidence cards`.
