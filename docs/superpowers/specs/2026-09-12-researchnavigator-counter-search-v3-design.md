# ResearchNavigator Multi-source Counter-search V3 Design

## Status

Approved architecture direction. This document changes the research-opportunity verification architecture; it does not itself authorize production database migration or production deployment.

## Current Production Baseline — 2026-09-12

V3 development must branch from the currently accepted R2.1 production line, not the older R2 checkpoint.

- `task_status`: `RN_PRODUCT_R2_ACCEPTANCE_PASS_WITH_TRANSLATION_CONFIG_BLOCKED`
- `execution_id`: `RN-R21-CLOSURE-20260912-5ad162b`
- `candidate_commit`: `5ad162bbf04b41480bc7e9a1d46f43dfb80c3379`
- `deployed_commit`: `5ad162bbf04b41480bc7e9a1d46f43dfb80c3379`
- `rollback_commit`: `f845cec2deafcb94a9d2f6d3c9c56f7af9183e0c`
- `deployment_id`: `9HjiuTYwh9VQNGZh6d3TY61z73sD`
- `deployment_status`: `READY`
- frontend / backend / database health: PASS (`200`, `ok`, `ok`)
- auth smoke: PASS
- OpenAlex smoke: PASS
- fixture detected: false
- Turso persistence: PASS
- research-topic UI / project context / global back / search-back restore / long-title layout / Chinese reading status: PASS
- unknown-vs-zero: PASS; UI shows bounded states such as `相关性待核验` instead of a false `0%`
- reproduction unknown state: PASS
- exploratory-question path: PASS with bounded next-step behavior
- strict-gap path: `NOT_TRIGGERED_SAFE_BOUNDARY`
- gap loading / duplicate-submit guard: PASS
- reading plan / exploration plan / plan persistence: PASS
- confirmed-gap plan: `NOT_TRIGGERED_SAFE_BOUNDARY`
- translation provider / real translation smoke: `BLOCKED_CONFIG`
- translation persistence: `NOT_RUN`
- original abstract preservation / translation evidence boundary: PASS
- account isolation / scientific claim boundary: PASS
- no migration was performed in the R2.1 closure task
- no Vercel environment/config change was performed in that closure task
- production deployment succeeded
- secret exposure: none
- remaining non-blocking R2.1 item: configure a legal `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` to verify real translation persistence separately
- previous next action: `WAITING_FOR_R2_TRANSLATION_CONFIGORIZATION`

V3 must preserve these accepted behaviors. Translation configuration remains an independent non-blocking track unless V3 code touches translation behavior.

Production database schema is currently `0009`. V3 does **not** pre-authorize `0010`; implementation must complete a schema-impact review first.

## Goal

Evolve ResearchNavigator from a workflow that primarily reasons over user-selected papers into a workflow that uses selected papers as **seed evidence**, then actively performs **multi-source counter-search** to discover existing work that may weaken or overturn a candidate research opportunity.

The system must not equate "open full text" with "searchable scholarly work". Paid or closed-access papers may still participate in counter-search when reliable public metadata or abstracts are available. Lack of legal full-text access limits the strength of claims the system may make; it does not erase the paper from the evidence set.

## Product Principle

> Evidence access level controls claim strength, not whether a paper is allowed to exist in the counter-evidence set.

ResearchNavigator must distinguish:

1. **Discoverability** — whether a paper can be reliably identified as existing and potentially relevant.
2. **Evidence accessibility** — how much legally accessible content is currently available for verification.

The product must continue to preserve these claim boundaries:

- "not found in the covered sources" is not "nobody has studied it";
- metadata-only evidence cannot support method, experiment, limitation, or Future Work claims;
- abstract evidence supports only what the abstract actually states;
- machine translation is reading assistance, not original scholarly evidence;
- full-text claims require legally accessible full text and traceable locations;
- a candidate research opportunity is never a novelty proof;
- human confirmation is required before a strict evidence-backed gap becomes an execution claim.

## Scope

### Phase 1 — approved for implementation planning

1. Add **Papers.cool** as an optional source in ordinary paper search.
2. Add **Papers.cool** as a default supplementary discovery source in counter-search when safely configured.
3. Refactor counter-search to use multiple scholarly discovery sources, not only open-full-text sources.
4. Allow paid/closed-access papers to enter counter-evidence classification when metadata and/or abstracts are legally accessible.
5. Separate paper discovery from evidence escalation.
6. Add source-aware paper identity resolution and conservative deduplication.
7. Add counter-evidence classes and evidence-access classes.
8. Use a ranking objective specific to counter-search: "most likely to overturn or narrow the candidate question" rather than normal reading relevance.

### Phase 2 — explicitly deferred

- DBLP integration.
- General Web Search as a supplementary counter-search layer.
- Citation graph crawling beyond currently available legal APIs.
- Broad publisher-specific scraping.
- Any bypass of authentication, paywalls, robots restrictions, or API terms.

## User-facing Workflow

1. **Seed Papers** — user-selected papers define the current task, methods, limitations, and candidate question.
2. **Candidate Question** — the system forms a bounded, falsifiable question; it does not yet call this a field-wide gap.
3. **Multi-source Counter-search** — search OpenAlex, Semantic Scholar, Crossref, arXiv, and Papers.cool according to safe source availability and configuration.
4. **Identity Resolution** — merge duplicate scholarly works conservatively while retaining source provenance.
5. **Evidence Access Classification** — determine what legal evidence is available for each work.
6. **Counter-evidence Classification** — distinguish verified counterexamples, high-risk potential counterexamples, related work needing verification, metadata-only leads, and low-risk background.
7. **Evidence Escalation** — for the most dangerous candidates, attempt lawful evidence enrichment via public abstract, OA copy, author preprint, publisher abstract, or user-provided material.
8. **Research Opportunity Decision** — retain, weaken/reframe, require more verification, or overturn the candidate question.

## Data Sources

### Ordinary paper search

Ordinary search may use:

- OpenAlex
- arXiv
- Crossref
- Semantic Scholar
- Papers.cool

Papers.cool is a **supplementary discovery source**, particularly useful for AI/CS conference and arXiv coverage. It must not be treated as the single authority for bibliographic truth.

### Counter-search

Counter-search should use broader coverage than normal search. Where configured and available, it should query:

- OpenAlex
- Semantic Scholar
- Crossref
- arXiv
- Papers.cool

Source failures must remain visible. One successful source must not mask another source's failure.

## Papers.cool Integration Rules

Papers.cool has two roles:

1. normal discovery for AI/CS conference and arXiv papers;
2. counter-search discovery for work that may challenge a candidate question.

Constraints:

- prefer a documented/publicly supported access mechanism that complies with the site's terms;
- do not build high-frequency scraping or anti-bot bypasses;
- treat Papers.cool records as discovery evidence until identity is corroborated where possible;
- preserve `source="papers_cool"` provenance;
- if a result maps to DOI, arXiv, or official proceedings, link those identities into the merged work record;
- expose source failure in source status;
- if no stable, terms-compliant programmatic access contract can be established, mark the source `BLOCKED_SOURCE_ACCESS_CONTRACT` and do not invent an unsupported scraper.

## Evidence Access Levels

Every discovered work should have an access classification independent of relevance:

- `metadata_only`
- `abstract_available`
- `open_fulltext`
- `publisher_fulltext_unavailable`
- `user_uploaded_fulltext`
- `publisher_authorized_fulltext`

### `metadata_only`

May support only existence, bibliographic identity, broad topic relevance, and a recommendation to verify further. It cannot support hidden method, experiment, limitation, or Future Work claims.

### `abstract_available`

May support research problem, task definition, broad method family, claimed contribution, major result if explicitly stated, and whether the paper plausibly overlaps the candidate question. It cannot support details absent from the abstract.

### full-text levels

Full-text claims require legally accessible content and the existing citation-location contract.

## Counter-evidence Classes

- `verified_counterexample` — accessible evidence directly supports materially equivalent coverage of the candidate question.
- `high_risk_potential_counterexample` — title/abstract/metadata strongly suggests overlap, but current evidence cannot prove equivalence.
- `related_work_needs_verification` — relevant work whose relationship to the candidate question is unresolved.
- `metadata_only_lead` — only bibliographic evidence is available; still retained as a risk signal.
- `background_low_risk` — broadly relevant but unlikely, on current evidence, to overturn the candidate question.

The system must never drop a high-risk paper merely because full text is unavailable.

## Ranking Objectives

### Normal search

Normal search ranks for reading utility: direction relevance, recency, venue/context signals, OA convenience, and user preference.

### Counter-search

Counter-search ranks for falsification risk:

> Which discovered works are most likely to disprove, narrow, or materially overlap the candidate question?

Signals may include task overlap, research-question overlap, direct title/abstract matches, method/target overlap, recent work, reviews/surveys, citation-neighbor signals when safely available, and source diversity.

Open-access availability is a verification-convenience signal, not a strong relevance signal in counter-search.

## Identity Resolution

A single scholarly work may appear in several sources. Produce one merged work view while retaining all source provenance.

Identity precedence:

1. exact DOI;
2. exact arXiv ID;
3. stable official source ID where appropriate;
4. normalized title + author overlap + year/venue consistency.

Ambiguous matches remain separate.

The current code already supports `Paper.source_provenance`, persistent `PaperSource` rows, DOI/arXiv normalization, and conservative title/year fallback. V3 should extend these contracts rather than replace them.

## Candidate Decision States

After counter-search, a candidate question may become:

- `retained_for_validation`
- `weakened_or_narrowed`
- `requires_more_verification`
- `overturned_by_counterevidence`

The UI must explain which papers drove the decision and which sources were actually covered.

Allowed language:

> "Across the currently covered sources, no directly verified counterexample was found; several potential counterexamples still require verification."

Forbidden language:

> "No one has studied this."

## UI Design

### Search page

Add Papers.cool to the source selector and per-source query editor only when the source is implemented/configured. Results continue to show provenance and access status separately.

### Counter-search page

Show:

- covered sources and per-source status;
- unique works discovered;
- evidence-access distribution;
- counter-evidence distribution;
- highest-risk papers first;
- explicit unresolved uncertainty.

For a paid paper with an accessible abstract, show the bibliographic record, `abstract_available`, why it may overlap the candidate question, what cannot be verified, and actions such as locating an OA version, opening the official record, or marking it for verification.

## Failure and Partial Coverage

Source status should support at least:

- `ok`
- `rate_limited`
- `timeout`
- `error`
- `disabled`
- `not_configured`
- `blocked_access_contract`

A source failure reduces coverage/confidence but does not erase successful results from other sources.

## Security, Copyright, and Access Rules

- No paywall bypass.
- No institutional-login automation.
- No robots/anti-bot bypass.
- No redistribution of closed full text.
- Metadata and abstracts are used only when legally exposed by the source and permitted by its access contract.
- User-uploaded full text still requires rights confirmation.
- Secrets remain server-side.

## Current Implementation Seams to Reuse

The accepted R2.1 code already provides useful seams:

- `ScholarlyAdapter` and `FederatedSearchService` for source adapters and federated source status.
- `SearchRequest.sources` and `source_queries` for per-source control.
- `PaperRecord.source_provenance` and `PaperSource` for multi-source provenance.
- DOI/arXiv/title normalization and deduplication in `scholarly/normalize.py`.
- `GapCandidate.counter_evidence_json`, `data_sources_json`, `coverage_json`, `GapEvidence`, and `AgentRun` for bounded counter-search persistence.

Phase 1 should prefer reusing these seams.

## Migration Strategy

Do **not** pre-authorize `0010`.

Schema-impact review must first test whether V3 can persist its required state using the existing `0009` schema. The default design preference is **no new migration** because the current schema already has:

- durable paper metadata and per-source provenance;
- durable gap counter-evidence JSON;
- source coverage JSON;
- per-paper gap evidence roles/rationale/source query;
- durable workflow/run snapshots through `AgentRun`.

A new migration is justified only if implementation proves an essential durable concept cannot be represented safely without one.

## Evaluation Plan

Phase-1 acceptance requires:

1. Papers.cool appears as an ordinary-search source when the integration is safely enabled.
2. Papers.cool participates in counter-search when safely configured.
3. Same-paper records from multiple sources deduplicate without losing provenance.
4. A closed-access paper with a public abstract can become a high-risk or verified counterexample when the abstract itself supports that classification.
5. A metadata-only paid paper remains visible as `metadata_only_lead`.
6. Lack of full text never becomes evidence that the work does not cover the candidate question.
7. Counter-search ranking differs from normal-search ranking.
8. Source failures remain visible and reduce source coverage.
9. No unsupported Papers.cool scraping is introduced.
10. Existing R2.1 claim-boundary, account-isolation, search-state, plan, loading, and unknown-vs-zero tests remain green.
11. Translation remains non-blocking and is not silently claimed as configured.

## Release Strategy

1. Branch implementation from `5ad162bbf04b41480bc7e9a1d46f43dfb80c3379`.
2. Use an isolated worktree and TDD.
3. Keep Production schema `0009` unchanged until schema-impact review completes.
4. Establish Papers.cool's safe source-access contract before implementing a production adapter.
5. Validate ordinary search and counter-search separately.
6. Validate source-failure and claim-boundary behavior.
7. Stop at a local V3 checkpoint before any Production Turso/Vercel change.
8. If Papers.cool cannot be safely integrated, the broader multi-source counter-search architecture may still proceed, but Papers.cool must remain `BLOCKED_SOURCE_ACCESS_CONTRACT`, not PASS.

## Non-goals

- proving global novelty;
- enumerating every paper on the internet;
- accessing paywalled full text without authorization;
- replacing scholarly indexes with generic web search;
- DBLP/Web Search in Phase 1;
- GraphRAG or autonomous-agent expansion;
- maximizing the number of generated gaps.

## Success Definition

A user can start from a few seed papers, form a candidate research question, and have ResearchNavigator actively search multiple scholarly sources for work that could invalidate it — including closed-access work discoverable through metadata or abstracts — while clearly separating existence, accessible evidence, counter-evidence strength, source coverage, and unresolved uncertainty.
