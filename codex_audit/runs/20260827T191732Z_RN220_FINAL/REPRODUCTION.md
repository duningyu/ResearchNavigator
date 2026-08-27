# ResearchNavigator 2.2.0 reproduction commands

Run from the repository root.

```bash
python --version
node --version
uv --version

git status --short
git log --oneline -25

uv lock --check
uv sync --frozen --extra dev

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=apps/api:. \
  python -m pytest -q -p pytest_asyncio.plugin
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=apps/api:. \
  python -m pytest -q -p pytest_asyncio.plugin tests/security tests/rag_eval

python -m compileall -q apps/api services mcp_servers scripts
ruff check apps/api services mcp_servers scripts tests
mypy apps/api/research_navigator services mcp_servers

PYTHONPATH=apps/api:. python scripts/export_openapi.py --output delivery/OPENAPI.json
node scripts/check_frontend_syntax.cjs

corepack enable
cd apps/web
corepack pnpm install --frozen-lockfile
corepack pnpm run typecheck
corepack pnpm test
corepack pnpm run build
corepack pnpm run test:e2e
cd ../..

python scripts/verify_mcp_stdio.py
python scripts/verify_live_sources.py --output /tmp/rn-live-sources.json
python scripts/verify_docker_persistence.py --output /tmp/rn-docker-persistence.json

python scripts/package_release.py \
  --name ResearchNavigator_2.2.0_evidence_platform_2026-08-28 \
  --output-dir /mnt/data
```

Do not promote a BLOCKED command to PASS without current command output.
