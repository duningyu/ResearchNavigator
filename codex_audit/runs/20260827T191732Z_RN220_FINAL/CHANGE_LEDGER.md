# ResearchNavigator 2.2.0 change ledger

Audited implementation commit: `a786c5b5359077b4fb63e7794cbb03bbc9d61f78`
Branch: `main`
Authoritative run: `codex_audit/runs/20260827T191732Z_RN220_FINAL`

| Commit | Single auditable claim |
|---|---|
| `74e9c94` | feat(db): add 2.2 evidence platform schema |
| `416467a` | feat(search): persist OpenAlex cooldown and fallback state |
| `83b2c4c` | feat(oa): resolve lawful fulltext candidates |
| `79c3945` | feat(oa): securely ingest permitted PDFs |
| `4b5bc3f` | feat(evidence): add resumable acquisition workflow |
| `fbb3f05` | feat(analysis): integrate citation-validated LLM enrichment |
| `ab75b6a` | feat(evidence): backfill legacy abstract provenance safely |
| `f903179` | feat(authors): add provenance-aware author cards |
| `0a1561b` | feat(datasets): add evidence-bounded dataset cards |
| `ef26b2d` | feat(map): add deterministic direction clustering |
| `ef9bea3` | feat(evals): add real-expert study workflow |
| `a12e575` | feat(evidence): refresh derived research cards |
| `d3a956a` | feat(web): surface evidence workflows and research intelligence |
| `502d0ad` | feat(evals): list and reopen owned studies |
| `551d65a` | feat(web): complete research map and expert evaluation workflows |
| `fba4ffd` | fix(jobs): mark partial evidence workflows terminal |
| `53fe937` | test(docker): add cold-start persistence acceptance harness |
| `401bc41` | feat(admin): expose provider status and safe abstract backfill |
| `c8f8e7d` | test(docker): harden persistence acceptance scenario |
| `1f85199` | fix(api): register evaluation routes once |
| `4df3322` | test(admin): cover expanded safe config status |
| `51db44e` | docs(release): define ResearchNavigator 2.2 evidence platform |
| `04830d3` | test(release): audit 2.2 evidence platform gates |
| `a786c5b` | docs(release): align 2.2 traceability and API contracts |

## Scope result

The requested implementation gaps now have production code and deterministic tests: lawful OA full-text resolution, persistent OpenAlex cooldown/fallback, LLM analysis/audit integration, author cards, dataset cards, deterministic direction clustering, expert-study infrastructure and safe historical abstract provenance backfill. Docker, live sources, live LLM, official MCP stdio, real expert outcomes and real historical backfill remain independent environment or real-world gates.
