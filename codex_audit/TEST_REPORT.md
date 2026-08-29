# ResearchNavigator 2.2.3 final release gate

- Targeted DOI tests: 4 passed.
- Backend: 188 passed.
- Security/RAG: 16 passed.
- Ruff: PASS.
- Mypy: PASS, 125 source files.
- Compileall: PASS.
- Alembic: PASS, head 0005, 53 tables, integrity ok.
- Frontend: frozen install, typecheck, 16 Vitest tests and build PASS.
- Playwright: 2/2 PASS with process, port and runtime cleanup.
- MCP: official stdio fresh-run PASS with isolated API.
- Live CASE B: HTTP 200, exact DOI, provenance, `requires_user_confirmation`, no ingest/promotion.

External/real-world validation remains explicitly partial or blocked.
