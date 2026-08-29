# RN222-OA-RESOLVE-001 closure

The exact DOI resolution bug is fixed on `bugfix/rn222-oa-resolve-001` at commit `e143e55f4b47500416e8f23cfa0a1c336dc58526`. The Frozen Core commit `4feee21824187ca60d15dded18703a593ff212cd` and its release ZIP were not modified.

## Verification

- RED: 3 expected DOI-routing failures and 1 text-search pass on the old implementation.
- GREEN: 4/4 targeted tests passed.
- Live CASE B: HTTP 200; exact DOI preserved; OpenAlex `cc-by-nc`; `requires_user_confirmation`; no auto-ingestion; evidence remained `abstract_only`.
- CASE A remains an external BMJ HTTP 403 and was not changed.
- CASE C remains correctly rejected as non-PDF.
- Backend: 188 passed; Security/RAG: 16 passed.
- Ruff, Mypy (125 files), compileall, Alembic (0005/53/ok), frontend install/typecheck/Vitest 16/build, and official MCP stdio verification passed.

## Release boundary

The full release gate is not complete because the existing E2E command starts API/Worker/Vite in `run-e2e.mjs` and then invokes a Playwright configuration with a second composite `webServer` stack. The second stack reuses the same isolated SQLite runtime and fails with `table session_tokens already exists`.

This is a separate pre-existing E2E infrastructure issue, not part of the DOI fix. Version remains 2.2.2; no 2.2.3 package was created. Current status is `PARTIAL`.
