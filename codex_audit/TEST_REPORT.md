# ResearchNavigator 2.2.2 verification closure

Final source commit: `9bd0a800d2a0f5d0c4312511c2f534d92ccefe14`

| Gate | Result |
|---|---|
| uv lock/check and frozen sync | PASS |
| backend pytest | 184 passed |
| security/RAG | 16 passed |
| Ruff | PASS |
| Mypy | PASS; 125 source files |
| compileall | PASS |
| Alembic | PASS; 0005 head, 53 tables, integrity ok |
| frontend install | PASS |
| frontend typecheck | PASS |
| Vitest | 16 passed |
| frontend build | PASS |
| Playwright | 2/2 passed |
| Playwright teardown | PASS; owned processes 0, ports released, runtime deleted |
| MCP official stdio | PASS; exit code 0 |

External boundaries: Docker is blocked by unavailable daemon; live LLM by missing configuration; live sources/OA smoke, real history backfill, and real expert validation were not claimed as PASS. Original input ZIP SHA256 provenance remains unresolved; source identity is verified by content fingerprint.
