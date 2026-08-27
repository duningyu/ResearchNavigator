# ResearchNavigator 2.2.0 acceptance report

## Conclusion

**PARTIAL.** The requested implementation gaps are closed at the production-code and deterministic-test level, while environment-dependent and real-world gates remain explicitly blocked.

## Implemented and regression-tested

1. Lawful OA candidate resolution, rights policy, secure remote PDF fetch and reuse of the existing parse/index/analysis pipeline.
2. Persistent OpenAlex rate-limit state, cooldown and source fallback without claiming OpenAlex live availability.
3. Deterministic-first LLM enrichment with field citations, fallback and secret-free `AgentRun`/`ToolCall` audit persistence.
4. Source-backed author cards with stable-identifier disambiguation and abstention for unresolved same-name authors.
5. Evidence-bounded dataset cards that do not invent splits, licenses or metrics.
6. Versioned deterministic direction clustering with input/parameter hash and user scope.
7. Blinded expert-study infrastructure that keeps simulated results separate from real expert validation.
8. Dry-run-first historical abstract provenance backfill with exact identity matching, idempotency, cancellation and no blanket promotion of old summaries.
9. Resumable evidence workflows, terminal `partial` semantics, UI progress/status/missing-field display, and backward compatibility for the legacy acquisition endpoint.
10. Docker persistence acceptance harness covering cold build, restart, down/up and backup/restore; actual container execution remains blocked on this host.

## Regression evidence

- Full backend suite: **184 passed**.
- New 2.2 focused matrix: **42 passed**.
- Security/RAG: **16 passed**.
- Schema: **Alembic 0005, 53 tables, integrity ok**.
- OpenAPI: **83 paths**, with all required 2.2 routes present.

## Unclosed external gates

See `GAP_LEDGER.csv`. No current PASS is claimed for Docker runtime persistence, dependency-aware frontend build/browser E2E, official MCP stdio, live scholarly sources, live OA acquisition, live LLM, real expert effects or real historical backfill outcomes.

## Audited implementation

- Commit: `a786c5b5359077b4fb63e7794cbb03bbc9d61f78`
- Branch: `main`
- Run: `codex_audit/runs/20260827T191732Z_RN220_FINAL`
