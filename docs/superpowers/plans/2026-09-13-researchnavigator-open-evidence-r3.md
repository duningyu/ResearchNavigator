# ResearchNavigator R3 Implementation Plan

Implementation base commit:
9705df6f4fc1be619f25d078c3c030051cfdb349

## Guardrails

- Work only in `feature/rn-product-r3-open-evidence-20260913`.
- Execute every package RED → GREEN → targeted regression → commit.
- Do not touch `deploy/researchnavigator-beta`, Production Turso, Vercel Production, secrets, migrations, or provider configuration.
- Reuse the existing PDF parser/index, PaperDocument, PaperAnalysisRecord, and storage abstractions.
- Do not bulk rewrite historical documents or analysis records.

## Task 1 — baseline and documents

Verify clean worktree and exact base commit. Keep the R3 design/spec files in the branch. Inspect existing scholarly adapters, document ingestion, analysis schemas/services/routes, PaperPage, and test layout before implementation.

## Task 2 — R3.1 RED: open evidence contracts

Add focused tests for `OpenMaterialCandidate`, fail-closed `classify_cache_policy`, arXiv identity binding, OpenAlex OA metadata preservation, bounded PDF validation, SSRF/private-target rejection, size/signature rejection, public document dedupe, and abstract fallback. Tests must prove existing user-upload behavior remains unchanged. Run the focused tests and record the expected RED failures before production code.

## Task 3 — R3.1 GREEN: acquisition and shared cache

Implement `documents/open_evidence.py`, `documents/remote_fetch.py`, and `documents/ingest.py`. Extend adapter records only with optional material metadata. Reuse parser/index/storage. Add application-level dedupe for shared public documents, persist provenance and rights fields, and keep ambiguous rights out of durable cache. Update acquisition and `/papers/{paper_id}/acquire-evidence` response with material outcome, cache hit, evidence levels, document id, and source type. Run OA-01..OA-10, related modules, and backend regression. Commit `feat: add bounded open evidence acquisition`.

## Task 4 — R3.2 RED: analysis cache identity

Add tests proving same user/paper/project/material/version/provider/model/prompt returns the existing analysis without another provider call; project or evidence changes reanalyse; prompt/version changes reanalyse; historical records are not modified. Run focused tests and verify RED.

## Task 5 — R3.2 GREEN: analysis reuse and status

Use `PaperAnalysisRecord` as the cache. Match user, paper, project, evidence hash, analysis version, provider, model, prompt, and compatible score versions. Expose analysis version/mode/evidence level/time/cache hit for the UI without bulk recomputation. Run focused and backend regressions. Commit `feat: reuse evidence analysis by material identity`.

## Task 6 — R3.3 RED: Chinese quick interpretation UI

Add tests for Chinese-first quick interpretation, collapsed original evidence, one-time expansion, citation dedupe, abstract-only/fulltext labels, provider-localization fallback, upload as optional enhancement, and narrow layout. Run focused tests and verify RED.

## Task 7 — R3.3 GREEN: structured display interpretation

Add display-only `QuickInterpretationZh` fields to analysis output and provider/schema validation. Generate concise Chinese paraphrases only from supported evidence; preserve original evidence and citation validation. A localization failure must leave the original evidence analysis usable. Add `QuickInterpretationPanel`, replace the raw quick-interpretation presentation on PaperPage, add analysis identity/material progress, and keep upload available as enhancement. Preserve R2 direction/reproduction semantics. Run focused, translation, R2, and frontend regressions. Commit `feat: add Chinese evidence-first quick interpretation`.

## Task 8 — bounded real-material acceptance

Run a local, non-Production evaluation over 30–50 real papers covering arXiv, OpenAlex OA, abstract-only, no-public-fulltext, and repeated papers. Record metadata/abstract/candidate/cache/manual rates and verify `wrong_document_binding_count=0` and `unauthorized_cache_count=0`. If either is nonzero, stop before any deployment action.

## Task 9 — final local gates and receipt

Run pytest, changed-file Ruff, mypy, frontend typecheck/Vitest/build, git diff check, and clean-worktree verification. Confirm translation tests, R2 plan semantics, direction-match-v3, and reproduction-v3 still pass. Push only the R3 feature branch after all gates; do not update deploy branch or Production. Return the complete R3 receipt and stop for review.
