# Security report — continuation run

- Application security/RAG boundary suite: PASS, 10/10 (`security-rag-green.log`).
- Cross-user browser isolation: PASS (`playwright-final.log`, test 2/2).
- MCP two-token isolation, missing-auth rejection, unavailable API and bounded timeout: PASS (`mcp-stdio-final.log`).
- PDF rights/MIME/signature/size and URL safety regressions are in `tests/security/test_document_security.py`.
- API/LLM secrets are not returned by the tested admin endpoints; new provider errors do not include API keys.
- Dependency vulnerability scan: BLOCKED because the required audit executable is unavailable in the current environment.
- Git-history secret scan: BLOCKED because `.git` metadata is absent.
- This report is an application security regression audit, not a penetration test.
