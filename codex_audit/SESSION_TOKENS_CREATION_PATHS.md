# `session_tokens` creation paths

- `apps/api/research_navigator/models.py`: `SessionToken.__tablename__ = "session_tokens"` defines the table.
- `apps/api/research_navigator/db.py:init()`: invokes `Base.metadata.create_all(self.engine)` during API lifespan startup. This is the table-creation path observed in the prior error stack.
- `apps/api/research_navigator/main.py` lifespan: calls the database initializer during API startup.
- `apps/api/alembic/versions/`: migrations are the schema migration path; no second `session_tokens` table definition was introduced by the DOI bugfix.
- `apps/web/scripts/run_e2e.mjs`: starts one API, one Worker, one Vite process and then a managed Playwright child.
- `apps/web/playwright.managed.config.ts`: contains no `webServer` block, so the official managed invocation does not start a second composite stack.

The current official command therefore has one E2E stack owner. The prior
`session_tokens already exists` event is not reproduced by either the frozen
control or the DOI bugfix candidate under fresh runtimes.
