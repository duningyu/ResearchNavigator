# ResearchNavigator 2.2.0 Evidence Platform Design

**Status:** Approved in conversation on 2026-08-28.

## 1. Objective

Close the remaining 2.1.1 gaps without weakening existing evidence, copyright, user-isolation, idempotency, and deterministic-fallback contracts. The release adds a versioned evidence workflow, lawful open-access discovery and PDF ingestion, persistent source throttling, optional LLM enrichment with citation validation, provenance-aware author and dataset cards, deterministic direction clustering, real-expert evaluation infrastructure, historical abstract provenance backfill, and Docker persistence acceptance tooling.

## 2. Compatibility contract

1. `POST /papers/{paper_id}/acquire-evidence` remains available with its current bounded metadata/abstract semantics.
2. Complete acquisition uses additive endpoints under `/evidence-workflows`; old clients remain valid.
3. Database changes are additive; existing rows are not silently relabelled as trustworthy.
4. `RN_ANALYSIS_PROVIDER=deterministic` is the default.
5. OpenAlex, OA resolution, remote PDF fetching, or LLM failure must not make deterministic analysis or other scholarly sources unavailable.
6. Existing user-uploaded or authorized full text takes precedence over remote acquisition.
7. New author cards, dataset cards, clusters, and evaluation records are optional page sections and cannot block existing paper detail responses.
8. Every new user-owned read and mutation is constrained by `user_id` and tested for cross-user denial.

## 3. Evidence workflow

A complete acquisition run is represented by an existing persistent `Job` with `job_type=evidence_workflow_v1` and ordered `JobEvent` records. The state sequence is:

`created → identity_resolution → abstract_acquisition → oa_location_discovery → license_policy → remote_pdf_fetch → pdf_security_validation → pdf_parse_and_index → deterministic_analysis → optional_llm_enrichment → author_card_refresh → dataset_card_refresh → direction_cluster_refresh → succeeded|partial|failed|cancelled`.

A step failure records an explicit code and reason. Recoverable external failures yield `partial`, preserving the strongest evidence already acquired. Cancellation is checked between steps.

Endpoints:

- `POST /api/papers/{paper_id}/evidence-workflows`
- `GET /api/evidence-workflows/{job_id}`
- `POST /api/evidence-workflows/{job_id}/cancel`
- `POST /api/evidence-workflows/{job_id}/run` for deterministic local execution and test harnesses

The worker registers the same handler for asynchronous execution.

## 4. Lawful OA resolution and PDF ingestion

OA candidates are resolved from DOI/arXiv identifiers using source-specific clients. A candidate contains source, stable source identifier, landing URL, PDF URL, license, host type, version, provenance hash, and a policy decision:

- `auto_ingest`: explicitly permissive/public-domain license.
- `requires_user_confirmation`: limited license where the user must confirm the intended lawful use.
- `link_only`: accessible URL but insufficient reuse/storage authorization.
- `rejected`: paywall, login, proxy, private host, invalid scheme, or policy violation.

The server never bypasses authentication, institutional proxies, robots controls, or publisher paywalls. Unknown license is never auto-ingested.

`SafePdfFetcher` validates every redirect hop, resolves DNS and rejects private/loopback/link-local/reserved addresses, strips user credentials and cookies, streams to a size limit, validates `Content-Type` and `%PDF-` magic, rejects HTML-as-PDF, and records final URL, response metadata hash, content SHA256, and retrieval time. It then reuses the existing PDF parser/indexer. OCR is not automatically enabled.

## 5. OpenAlex rate limiting

A global `source_runtime_states` row persists source health, cooldown, consecutive failures, rate-limit metadata, last HTTP status, and last error. OpenAlex responses expose non-secret rate-limit metadata through `SourceStatus.metadata`. HTTP 429 sets a bounded exponential cooldown with deterministic jitter for tests. Requests during cooldown return `rate_limited` without calling the network. Federated search continues with other configured sources. OpenAlex itself remains `rate_limited`/`degraded`; fallback success does not relabel it as PASS.

## 6. LLM analysis enrichment

Deterministic structured analysis always executes first and defines the evidence boundary. Optional providers are `openai_compatible` and `ollama`.

The LLM can only fill fields that are unknown and supported by supplied abstract/chunks. Every non-empty field requires one or more valid local citations. Invalid JSON, missing citations, cross-paper citations, inaccessible chunks, or evidence-level violations reject the LLM result and preserve deterministic output. Provider failures create `fallback_reason` and return deterministic analysis.

`PaperAnalysisRecord` stores analysis run, mode, provider, model, prompt version, input evidence hash, provider output hash, and fallback reason. `AgentRun` and `ToolCall` persist provider/model/prompt, bounded input identifiers/hashes, latency, attempts, token usage, response status, and validated output hash. Secrets and Authorization headers are never persisted.

## 7. Author cards

Source-backed tables store canonical author identity, ORCID/source IDs, affiliations, topics, counts, homepage, provenance, and `identity_status`. Authors are merged only by stable identifiers. Name-only candidates remain `unresolved`; the system does not infer individual contribution without CRediT evidence.

## 8. Dataset cards

Dataset cards and paper mentions retain raw mention, canonical name when verified, role, task, domain, access URL, license, split details, metrics, evidence level, field citations, provenance, and `identity_status`. Missing properties are not inferred. An abstract-only name mention cannot produce split or licensing claims.

## 9. Direction clustering

`direction-cluster-v1` is deterministic and local. It uses title, trusted abstract, concepts, fields of study, and evidenced analysis fields to build a hashing-vector cosine graph. Connected components above the configured similarity threshold become clusters. Runs persist algorithm version, parameters, input hash, cluster labels/terms, members, and evidence-level distribution. The UI states that clusters are literature-organization aids, not objective field taxonomies.

## 10. Expert evaluation infrastructure

The system implements frozen studies, tasks, randomized/blinded assignments, expert ratings, result aggregation, completion timing, evidence correctness, unsupported-claim rate, citation usefulness, missing-field correctness, preference, and inter-rater agreement. Simulation cannot set a study to verified. Until real external experts submit ratings, `expert_outcome_validation=awaiting_real_experts` or `BLOCKED`.

## 11. Historical abstract provenance backfill

Legacy `Paper.abstract` values remain untrusted. An admin-only idempotent job supports dry-run, batch size, source allow-list, cancellation, and resume. Each paper follows DOI exact match, arXiv ID exact match, then strict normalized title plus year. Fixture or identifier-conflicting results cannot set `PaperSource.provides_abstract=true`. Successful verified results update the paper only when appropriate and create a new analysis version. Full-text evidence is never downgraded.

## 12. Docker persistence acceptance

The release adds a dedicated acceptance compose file and script that builds without cache, starts API/worker/web, creates representative user-owned state through HTTP, restarts services, performs `down/up`, verifies database/uploads/chunks/analyses/jobs, executes backup and staged restore, and checks hashes plus SQLite integrity. A Docker PASS requires current-checkout command output; absent Docker remains `BLOCKED`.

## 13. Release and claim boundaries

Implementation may be claimed when code and deterministic tests pass. Live OpenAlex, Docker restart persistence, licensed sources, and real-expert outcomes are independently reported as PASS/FAIL/BLOCKED/SKIPPED based only on executed evidence. No source or expert claim is upgraded because fallback or fixture tests pass.
