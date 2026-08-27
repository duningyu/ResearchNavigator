# UI refresh deployment report

Date: 2026-08-27

## Scope and boundary

This is a post-audit visual release explicitly authorized by the user. It changes only the web presentation and navigation shell; it does not change API routes, persistence, evidence scoring, source provenance, authentication semantics, or the audit release-gate conclusion.

## Delivered experience

- Rebuilt the sign-in page as a responsive two-column research-workspace entry screen.
- Added the evidence-boundary statement before sign-in: candidate gaps are not novelty proof.
- Reworked the signed-in shell with a research-workflow sidebar, contextual header, and user identity area.
- Replaced the dashboard with a visible research start point, search/project actions, workflow steps, and an explicit claim-boundary notice.
- Applied shared card, table, and alert styling to the existing feature pages.

## Test-first evidence

The new `workspaceExperience.test.tsx` was first run against the prior interface and failed because the new hero and dashboard action were absent. After implementation, the following source-tree checks passed:

```text
node node_modules/vitest/vitest.mjs run --exclude tests/e2e/** --pool=forks --maxWorkers=1 --no-file-parallelism --reporter=dot
3 files passed, 6 tests passed

node node_modules/typescript/bin/tsc -b --pretty false
passed

node node_modules/vite/bin/vite.js build
passed
```

The production target at `E:\AI_Projects\ResearchNavigator` was rebuilt with `VITE_API_BASE_URL=http://127.0.0.1:8000/api`, then its static server was restarted on `127.0.0.1:8080`.

## Browser acceptance

After a fresh browser reload of `http://127.0.0.1:8080/`, the rendered sign-in page displayed `RESEARCH NAVIGATOR · 2.0` and the headline `把证据变成下一步研究决策`. This is direct runtime evidence that the new bundle—not the previous login card—is being served.

## Residual note

Vite reports a compressed JavaScript bundle of approximately 367 kB and emits its standard chunk-size warning. This is a performance follow-up, not a release blocker for the visual deployment.

## 2026-08-27 usability follow-up

- The desktop sidebar is now fixed while the content area scrolls; the existing responsive breakpoint retains the collapsed small-screen behavior.
- Compare and gap generation no longer accept opaque comma-separated internal paper IDs.
- Both workflows load the user's latest saved search session, display paper titles with year and venue, and require selection from that visible corpus. With no prior search, the interface links back to paper search.
- The comparison workspace now renders a field-by-paper matrix for year, authors, venue, identifiers, keywords, and the currently accessible abstract. Missing values are explicitly marked rather than inferred.
