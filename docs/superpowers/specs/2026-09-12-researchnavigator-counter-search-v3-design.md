# ResearchNavigator Multi-source Counter-search V3 Design

## Status

Approved product direction for design review. This document changes the architecture of research-opportunity verification; it does not authorize implementation, database migration, or production deployment.

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

### Phase 1 — this design

1. Add **Papers.cool** as an optional source in ordinary paper search.
2. Add **Papers.cool** as a default supplementary discovery source in counter-search.
3. Refactor counter-search to use multiple scholarly discovery sources, not only open-full-text sources.
4. Allow paid/closed-access papers to enter counter-evidence classification when metadata and/or abstracts are available.
5. Separate paper discovery from evidence escalation.
6. Add source-aware paper identity resolution and deduplication.
7. Add counter-evidence classes and evidence-access classes.
8. Use a ranking objective specific to counter-search: "most likely to overturn the candidate question" rather than normal reading relevance.

### Phase 2 — explicitly deferred

- DBLP integration.
- General Web Search as a supplementary counter-search layer.
- Citation graph crawling beyond currently available legal APIs.
- Broad publisher-specific scraping.
- Any bypass of authentication, paywalls, robots restrictions, or API terms.

## User-facing Workflow

The new workflow is:

1. **Seed Papers**
   - User selects papers from search, library, or comparison.
   - These papers help define the current task, methods, limitations, and candidate question.

2. **Candidate Question**
   - System proposes a bounded, falsifiable research question.
   - Example form: "Does method X remain effective under condition Y?"
   - The system does not yet call this a field-wide research gap.

3. **Multi-source Counter-search**
   - Search OpenAlex, Semantic Scholar, Crossref, arXiv, and Papers.cool according to source availability and configuration.
   - Search objective is high recall for potentially conflicting existing work.

4. **Identity Resolution**
   - Merge duplicate records using DOI, arXiv ID, stable source IDs, normalized title, authors, venue, and year.
   - Preserve per-source provenance instead of discarding source identities after merge.

5. **Evidence Access Classification**
   - Determine how much evidence is legally available for each work.

6. **Counter-evidence Classification**
   - Classify whether each discovered paper is a verified counterexample, high-risk potential counterexample, related work needing verification, metadata-only lead, or low-relevance background.

7. **Evidence Escalation**
   - For the most dangerous potential counterexamples, attempt lawful evidence enrichment: abstract, OA copy, author preprint, publisher abstract, or user-provided material.

8. **Research Opportunity Decision**
   - Candidate may be retained, weakened, reframed, or rejected.
   - UI always reports covered sources and unresolved uncertainty.

## Data Sources

### Ordinary paper search

Ordinary search may use:

- OpenAlex
- arXiv
- Crossref
- Semantic Scholar
- Papers.cool

Papers.cool is a **supplementary discovery source**, particularly useful for AI/CS conference coverage. It must not be treated as the single authority for bibliographic truth.

Users may enable/disable sources where the existing source-selection UI supports it. Search results should identify source provenance and deduplicate repeated works.

### Counter-search

Counter-search defaults to broader coverage than normal search. Where configured, it should query:

- OpenAlex
- Semantic Scholar
- Crossref
- arXiv
- Papers.cool

The system should continue if one source fails, but must report source-specific status. It must not silently replace a failed source with another and claim full coverage.

## Papers.cool Integration Rules

Papers.cool should serve two product roles:

1. **Normal discovery** — help users find AI/CS conference and arXiv papers.
2. **Counter-search discovery** — help surface relevant conference work that may challenge a candidate question.

Integration constraints:

- prefer any documented/publicly supported access mechanism that complies with the site's terms;
- do not build high-frequency scraping or anti-bot bypasses;
- treat Papers.cool records as discovery evidence until identity is corroborated where possible;
- preserve `source="papers_cool"` provenance;
- if a result maps to DOI/arXiv/official proceedings, link those identities into the merged work record;
- source failure must be visible in source status.

If no stable, terms-compliant programmatic access path is available, the implementation phase must stop this integration at `BLOCKED_SOURCE_ACCESS_CONTRACT` rather than inventing an unsupported scraper.

## Evidence Access Levels

Every discovered work should have an access classification independent of relevance:

- `metadata_only`
- `abstract_available`
- `open_fulltext`
- `publisher_fulltext_unavailable`
- `user_uploaded_fulltext`
- `publisher_authorized_fulltext`

### metadata_only

Allowed conclusions:

- work exists;
- title/author/year/venue/DOI/source identity;
- topic may be relevant;
- work should be manually verified.

Forbidden conclusions:

- method details;
- loss/objective;
- dataset protocol;
- limitations;
- Future Work;
- experimental superiority.

### abstract_available

May support only claims explicitly present in the abstract, such as:

- research problem;
- task definition;
- broad method family;
- claimed contribution;
- major result if stated in the abstract;
- whether the paper plausibly overlaps the candidate question.

It may not support hidden full-text details.

### full-text levels

Full-text claims require legally accessible content and existing citation-location contracts.

## Counter-evidence Classes

Counter-search results should be grouped as:

### `verified_counterexample`

Available evidence directly supports that the work covers the same or materially equivalent research question and therefore weakens or overturns the candidate opportunity.

### `high_risk_potential_counterexample`

Title/abstract/metadata strongly suggests overlap, but evidence is not sufficient to conclude equivalence. These results should be prioritized for further verification.

### `related_work_needs_verification`

Work is relevant but current evidence does not establish whether it actually covers the candidate question.

### `metadata_only_lead`

Only bibliographic metadata is available. It remains visible as a risk signal.

### `background_low_risk`

Relevant to the broad area but currently unlikely to overturn the candidate question.

The system must never drop a high-risk paper merely because full text is unavailable.

## Ranking Objectives

### Normal search ranking

Normal search can continue to optimize for reading utility, including:

- direction relevance;
- recency;
- venue;
- citation/context signals;
- open-access convenience;
- user preferences.

### Counter-search ranking

Counter-search requires a separate ranking objective:

> Which discovered works are most likely to disprove, narrow, or materially overlap the candidate question?

Ranking signals may include:

- task-definition overlap;
- research-question overlap;
- title/abstract direct match;
- method/target overlap;
- recent publications;
- surveys/reviews;
- citation-neighbor signals where available;
- source diversity.

Open-access availability must not be a strong positive relevance signal in counter-search. It affects verification convenience, not whether the work is dangerous to the hypothesis.

## Identity Resolution

A single scholarly work may appear in several sources. The system should produce one merged work view while retaining source provenance.

Identity precedence:

1. DOI exact match.
2. arXiv ID exact match.
3. stable official source ID where appropriate.
4. normalized title + author overlap + publication year/venue consistency.

Ambiguous matches must remain separate rather than being force-merged.

Merged records should retain:

- all contributing sources;
- source-specific URLs/IDs;
- best available metadata;
- evidence-access level;
- source confidence/verification notes.

## Candidate Decision States

After counter-search, a candidate question may become:

- `retained_for_validation`
- `weakened_or_narrowed`
- `requires_more_verification`
- `overturned_by_counterevidence`

The UI should explain why the state changed and which papers drove the decision.

The system must use bounded language such as:

> "Across the currently covered sources, no directly verified counterexample was found; several potential counterexamples still require verification."

It must not say:

> "No one has studied this."

## UI Design

### Search page

Add Papers.cool as a source label/selector where source selection is shown.

Each result should continue to show source provenance and OA/access status separately.

### Research opportunity / counter-search page

Show:

- covered sources;
- per-source status;
- number of discovered unique works;
- evidence-access distribution;
- counter-evidence distribution;
- highest-risk papers first.

Example summary:

- verified counterexamples: 3
- high-risk potential counterexamples: 6
- related work needing verification: 11
- metadata-only leads: 8

For a paid paper with an available abstract:

- show title, venue, DOI/source links;
- show `abstract_available`;
- explain why it may overlap the candidate question;
- show what cannot be verified without stronger evidence;
- offer actions such as "find open version", "open official record", "mark for verification".

## Failure and Partial Coverage

Source failure is not total-system failure.

Each source must expose a status such as:

- `ok`
- `rate_limited`
- `timeout`
- `error`
- `disabled`
- `blocked_access_contract`

The final candidate decision must display which sources were actually searched.

A source failure may reduce coverage/confidence, but must not be hidden.

## Security, Copyright, and Access Rules

- No paywall bypass.
- No institutional-login automation.
- No robots or anti-bot bypass.
- No redistribution of closed full text.
- Metadata and abstracts may be used only where legally exposed by the source and permitted by the source contract.
- User-uploaded full text continues to require rights confirmation.
- Secrets remain server-side.

## Evaluation Plan

Implementation is not accepted merely because more papers are returned.

Phase-1 acceptance should test:

1. Papers.cool appears as a normal-search source when enabled.
2. Papers.cool participates in counter-search by default when configured.
3. The same paper from multiple sources is deduplicated without losing provenance.
4. A closed-access paper with an accessible abstract can become a high-risk or verified counterexample when the abstract supports that conclusion.
5. A metadata-only closed-access paper remains visible as `metadata_only_lead`.
6. Lack of full text never becomes evidence that the work does not cover the candidate question.
7. Counter-search ranking differs from normal reading ranking.
8. Source failures are visible and reduce coverage instead of being silently ignored.
9. No unsupported source scraping is introduced.
10. Existing claim-boundary tests continue to pass.

## Migration Strategy

Phase 1 should first attempt to reuse the existing `Paper`, `PaperSource`, search-session, comparison, and gap evidence models.

A new database migration is justified only if the existing schema cannot represent one of these required durable concepts:

- counter-search run identity and source coverage;
- counter-evidence classification;
- merged multi-source provenance that cannot be represented by current `PaperSource` records;
- access-level state that must persist independently of existing paper/document fields.

Do not pre-authorize an `0010` migration. The implementation plan must perform a schema-impact review before deciding whether a migration is necessary.

## Release Strategy

1. Implement in an isolated feature worktree from the currently accepted R2 code line.
2. Keep current Production database schema `0009` unchanged until schema-impact review is complete.
3. Build and validate Papers.cool integration separately before enabling it in Production.
4. Validate ordinary search and counter-search independently.
5. Run source-failure tests and claim-boundary tests.
6. Deploy only after a live source smoke proves that Papers.cool access is real and terms-compliant.
7. If live Papers.cool access cannot be established safely, ship the broader multi-source counter-search architecture without claiming Papers.cool integration as PASS.

## Non-goals

This phase does not attempt to:

- prove global novelty;
- enumerate every paper on the internet;
- access paywalled full text without authorization;
- replace scholarly indices with generic web search;
- introduce GraphRAG, autonomous agents, or unrelated research-assistant features;
- optimize for the number of generated "gaps".

## Success Definition

The product succeeds when a user can start from a few seed papers, form a candidate research question, and have ResearchNavigator actively search multiple scholarly sources for work that could invalidate that question — including closed-access work discoverable through metadata or abstracts — while clearly separating discovered existence, accessible evidence, counter-evidence strength, and unresolved uncertainty.
