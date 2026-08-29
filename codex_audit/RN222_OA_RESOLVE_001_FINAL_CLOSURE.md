# RN222-OA-RESOLVE-001 final closure

Status: CLOSED in ResearchNavigator 2.2.3.

The resolver now canonicalizes DOI input and performs exact provider lookup
with exact-provider fallback before broad textual search. Targeted regression,
full backend, security/RAG, static checks, database migration, frontend,
Playwright, MCP and live CASE B verification passed.

CASE B retains `cc-by-nc`, requires user confirmation, performs no automatic
ingestion, and does not promote evidence. CASE A remains an external 403 and
is outside this bug's scope.
