# ResearchNavigator 2.2.0 implementation ledger

| Capability | Implementation state | Current external/experience gate | Claim boundary |
|---|---:|---:|---|
| Lawful OA resolver and secure PDF ingestion | PASS | Live OA BLOCKED | Reachability is not authorization; unknown rights are link-only/rejected. |
| OpenAlex cooldown and fallback | PASS | OpenAlex live BLOCKED | Fallback success is not OpenAlex availability. |
| LLM analysis API + audit | PASS | Live provider BLOCKED | Deterministic fallback remains default; no live model result is claimed. |
| Historical abstract provenance backfill | PASS | Real runtime outcome BLOCKED | Existing abstract text is not trusted without reacquisition. |
| Author cards | PASS | Browser E2E BLOCKED | Same-name authors are unresolved without stable IDs. |
| Dataset cards | PASS | Browser E2E BLOCKED | Missing split/license/metric data remains unknown. |
| Direction clustering | PASS | Browser E2E BLOCKED | It is deterministic literature organization, not an objective field taxonomy. |
| Expert evaluation infrastructure | PASS | Real expert outcome BLOCKED | Simulated ratings never unlock real-expert status. |
| Evidence workflow + worker | PASS | Real deployment monitoring pending | `partial` is terminal but not full success. |
| Docker persistence harness | PASS | Actual Docker BLOCKED | Script/contracts do not replace a container run. |
| Existing search/library/compare/gap/plan/backup flows | PASS in backend regression | Current browser E2E BLOCKED | Prior 2.1 browser evidence is not reused as current 2.2 PASS. |
| Commercial licensed sources | SKIPPED | SKIPPED | No unauthorized integration. |
