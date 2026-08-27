# ResearchNavigator Agent Contract

## Authority order

1. `docs/APPROVED_MASTER_PROMPT.txt` — approved product requirements and claim boundaries.
2. `AGENTS.md` — repository execution rules.
3. `CODEX_AUDIT_AND_COMPLETION_PROMPT.md` — audit and completion workflow.
4. `docs/superpowers/specs/2026-08-26-research-navigator-design.md` — architectural decisions.
5. `docs/requirement-traceability.md` and `delivery/STATUS.json` — claims to verify, **not sources of truth**.

When documents conflict, preserve the stricter evidence, privacy, authorization, and non-inflation rule.

## Product invariant

ResearchNavigator is an evidence-grounded research-direction and paper workspace. It is not a novelty oracle. Never emit or document a claim that a research problem is definitely unstudied. Gap candidates must retain:

- search scope and sources;
- supporting, adjacent, and potential counter-evidence;
- challenge queries and completion state;
- evidence coverage and confidence;
- `not_novelty_proof=true`;
- human confirmation before plan generation.

## Evidence invariant

- `metadata_only`: metadata only.
- `abstract_only`: do not infer full-text architecture, losses, hyperparameters, experiments, Future Work, or limitations not present in the abstract.
- `open_fulltext`, `user_uploaded_fulltext`, `publisher_authorized_fulltext`: may extract only from the accessible content and must cite section/page/chunk/source.
- Unknown data is `unknown`, not automatically `missing`.
- Fixture data is never real scholarly evidence and must remain visibly marked.

## Access and copyright invariant

Do not bypass authentication, institutional proxies, robots controls, publisher paywalls, or API terms. Do not scrape licensed pages through simulated login. API keys remain server-side. User-uploaded PDFs require explicit rights confirmation. URL fetchers must resist SSRF, redirects to private networks, HTML-as-PDF, oversized content, path traversal, and malicious filenames.

## User isolation invariant

All user-owned reads and mutations must constrain `user_id`. Global paper metadata may be shared; profiles, projects, searches, notes, favorites, tags, reading status, uploads, analyses, recommendations, gaps, plans, jobs, tool calls, and audit records may not leak across users. Every new user-scoped endpoint requires a cross-user denial test.

## Engineering workflow

1. Read the approved prompt, current status, test report, and gap ledger.
2. Establish a clean baseline. Do not edit before recording baseline commands and outputs.
3. For every behavior change, use RED → GREEN → REFACTOR. A test that never failed is not evidence of the change.
4. Work in small commits with one auditable purpose.
5. Re-run focused tests after each change and the full gates before completion.
6. Do not delete failing tests, weaken assertions, or relabel real failures as environment limitations.
7. Do not mutate fixture expectations to manufacture passing metrics.
8. Never claim an external source is integrated unless a live, provenance-preserving integration test passed.
9. Never claim Docker, browser E2E, MCP stdio, or restart persistence passed without actual command output.
10. Update `docs/requirement-traceability.md`, `docs/claim-boundary.md`, `delivery/STATUS.json`, and `delivery/TEST_REPORT.md` only after verification.

## Required baseline commands

```bash
python --version
node --version
uv --version

git status --short
git log --oneline -15

uv sync --extra dev
pytest -q
ruff check apps/api services mcp_servers scripts tests
mypy apps/api/research_navigator services mcp_servers

cd apps/web
corepack enable
pnpm install --frozen-lockfile
pnpm run typecheck
pnpm test
pnpm run build
cd ../..

PYTHONPATH=apps/api:. python scripts/export_openapi.py --output delivery/OPENAPI.json
```

If a command cannot run, preserve the exact command, exit code, and blocker in the report. `BLOCKED`/`SKIPPED` are acceptable when justified; fabricated PASS is not.

## Release gates

A capability may be `PASS` only when its acceptance command ran in the current checkout. Use:

- `PASS`: command executed and assertions passed;
- `FAIL`: command executed and failed;
- `BLOCKED`: prerequisite/executable/dependency/network/credentials unavailable;
- `SKIPPED`: explicitly outside authorized/implemented release scope;
- `PARTIAL`: a narrower contract passed while a required end-to-end gate did not;
- `NOT_IMPLEMENTED`: no production implementation exists.

`IMPLEMENTED_NOT_ENV_VERIFIED` is documentation shorthand, not a release PASS.

## Protected files and history

- Do not rewrite `docs/APPROVED_MASTER_PROMPT.txt`.
- Do not erase prior `delivery/` evidence; write a new timestamped run under `codex_audit/runs/<timestamp>/` before updating the current summary.
- Do not force-push, squash away audit history, or modify user secrets.
- Do not commit `.env`, runtime databases, uploaded PDFs, API keys, real user data, browser storage state, or licensed full text.

## Final response contract

Report, in this order:

1. audited commit and environment;
2. baseline failures found;
3. changes made, one claim per commit;
4. exact test/build/deployment/MCP/live-source results;
5. unresolved gaps and why they remain;
6. changed claim boundary;
7. reproduction commands;
8. paths to `codex_audit/FINAL_STATUS.json`, `TEST_REPORT.md`, `GAP_LEDGER.csv`, and `CHANGE_LEDGER.md`.

No completion claim may be stronger than the evidence in those files.
