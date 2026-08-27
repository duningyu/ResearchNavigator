# ResearchNavigator 2.1.0 Verification Report

- Generated (UTC): `2026-08-27T10:17:10.639842+00:00`
- Git metadata: `unavailable: uploaded delivery contains no .git metadata`
- Overall status: **PARTIAL**

`PARTIAL` means deterministic gates passed but at least one required environment-dependent gate is BLOCKED. It is not equivalent to production readiness.

## Check matrix

| Check | Status | Exit | Duration | Command / blocker |
|---|---:|---:|---:|---|
| `backend_pytest` | **PASS** | 0 | 24.064s | /opt/pyvenv/bin/python -m pytest -q |
| `python_compileall` | **PASS** | 0 | 0.565s | /opt/pyvenv/bin/python -m compileall -q apps/api services mcp_servers scripts |
| `openapi_export` | **PASS** | 0 | 1.818s | /opt/pyvenv/bin/python scripts/export_openapi.py --output /mnt/data/researchnavigator_impl/src/ResearchNavigator_2.0.0-rc1_full_package_2026-08-27/codex_audit/runs/20260827T101632Z/OPENAPI.json |
| `alembic_upgrade` | **PASS** | 0 | 1.601s | alembic upgrade head |
| `backup_restore_export_roundtrip` | **PASS** | 0 | 3.875s | /opt/pyvenv/bin/python scripts/seed_demo.py --database /tmp/rn-backup-kje2mn3j/runtime/research_navigator.db --email verification@example.invalid --password verification-only-password-123 && /opt/pyvenv/bin/python scripts/export_workspace.py --database /tmp/rn-backup-kje2mn3j/runtime/research_navigator.db --email verification@example.invalid --output /tmp/rn-backup-kje2mn3j/workspace.json && /opt/pyvenv/bin/python scripts/backup.py --runtime /tmp/rn-backup-kje2mn3j/runtime --output /tmp/rn-backup-kje2mn3j/backup.zip && /opt/pyvenv/bin/python scripts/restore.py /tmp/rn-backup-kje2mn3j/backup.zip --runtime /tmp/rn-backup-kje2mn3j/restored --force |
| `http_first_acceptance` | **PASS** | 0 | 3.141s | /opt/pyvenv/bin/python scripts/run_acceptance_scenario.py --scenario-version feedback-closure-v1 --output /mnt/data/researchnavigator_impl/src/ResearchNavigator_2.0.0-rc1_full_package_2026-08-27/codex_audit/runs/20260827T101632Z/HTTP_ACCEPTANCE.json |
| `ruff` | **BLOCKED** | None | 0.0s | ruff executable is unavailable |
| `mypy` | **BLOCKED** | None | 0.0s | mypy executable is unavailable |
| `frontend_syntax_transpile` | **PASS** | 0 | 1.198s | node scripts/check_frontend_syntax.cjs apps/web |
| `frontend_typecheck` | **BLOCKED** | None | 0.0s | apps/web/node_modules is absent and dependency installation cannot be completed in the current offline/DNS-constrained environment |
| `frontend_unit_tests` | **BLOCKED** | None | 0.0s | apps/web/node_modules is absent and dependency installation cannot be completed in the current offline/DNS-constrained environment |
| `frontend_build` | **BLOCKED** | None | 0.0s | apps/web/node_modules is absent and dependency installation cannot be completed in the current offline/DNS-constrained environment |
| `playwright_e2e` | **BLOCKED** | None | 0.0s | apps/web/node_modules is absent and dependency installation cannot be completed in the current offline/DNS-constrained environment |
| `docker_compose_config` | **BLOCKED** | None | 0.0s | docker executable is unavailable |
| `docker_cold_start` | **BLOCKED** | None | 0.0s | docker executable is unavailable |
| `mcp_sdk_import` | **BLOCKED** | None | 0.0s | Traceback (most recent call last):
  File "<string>", line 1, in <module>
    import mcp; print('official MCP SDK import PASS')
    ^^^^^^^^^^
ModuleNotFoundError: No module named 'mcp'
 |
| `mcp_stdio` | **BLOCKED** | None | 0.0s | official MCP SDK is unavailable |
| `live_open_sources` | **BLOCKED** | None | 0.0s | live network smoke was not requested; deterministic regression uses fixture sources |
| `licensed_sources` | **SKIPPED** | None | 0.0s | licensed adapters are outside the implemented source set and no lawful credentials were supplied |
| `uv_lock_check` | **PASS** | 0 | 0.023s | uv lock --check |

## Exact outputs

### backend_pytest — PASS

```text
........................................................................ [ 76%]
......................                                                   [100%]
94 passed in 21.13s
```

### python_compileall — PASS

```text
(no output)
```

### openapi_export — PASS

```text
/mnt/data/researchnavigator_impl/src/ResearchNavigator_2.0.0-rc1_full_package_2026-08-27/codex_audit/runs/20260827T101632Z/OPENAPI.json
```

### alembic_upgrade — PASS

```text
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, Frozen explicit initial ResearchNavigator schema.
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, Add minimum traceable audit infrastructure.
INFO  [alembic.runtime.migration] Running upgrade 0002 -> 0003, Add feedback-closure search, selection, comparison, settings, and idempotency schema.
```

### backup_restore_export_roundtrip — PASS

```text
{"export_email": "verification@example.invalid", "archive_entries": ["backup-manifest.json", "research_navigator.db"], "backup_format_version": 2, "restored_users": 1, "restored_projects": 1, "sqlite_integrity": "ok", "credentials_omitted": true}
```

### http_first_acceptance — PASS

```text
{
  "scenario_version": "feedback-closure-v1",
  "execution_mode": "http_api_only_after_bootstrap",
  "user_id": 1,
  "project_id": 1,
  "search": {
    "session_id": 1,
    "mode": "discovery",
    "requested_limit": 50,
    "actual_count": 5,
    "diversity_seed": "035b16dd38812a7edab04c7bd10f76c8",
    "composition": {
      "requested_limit": 50,
      "classic_target": 10,
      "frontier_target": 40,
      "classic_count": 0,
      "frontier_count": 5,
      "fill_count": 0,
      "classic_shortfall": 10,
      "frontier_shortfall": 35,
      "candidate_pool_count": 5,
      "rule_version": "discovery-ranking-v1",
      "rankings": {
        "1": {
          "label": "frontier_candidate",
          "relevance": 4.0,
          "rank_score": 4.0,
          "relevance_band": 400,
          "position": 1
        },
        "2": {
          "label": "frontier_candidate",
          "relevance": 4.0,
          "rank_score": 4.0,
          "relevance_band": 400,
          "position": 2
        },
        "3": {
          "label": "frontier_candidate",
          "relevance": 4.0,
          "rank_score": 4.0,
          "relevance_band": 400,
          "position": 3
        },
        "4": {
          "label": "frontier_candidate",
          "relevance": 3.0,
          "rank_score": 3.0,
          "relevance_band": 300,
          "position": 4
        },
        "5": {
          "label": "frontier_candidate",
          "relevance": 2.0,
          "rank_score": 2.0,
          "relevance_band": 200,
          "position": 5
        }
      },
      "mode_rule_version": "search-mode-v1"
    }
  },
  "paper_set": {
    "id": 1,
    "paper_ids": [
      1,
      2
    ]
  },
  "comparison": {
    "id": 1,
    "row_count": 19,
    "evidence_hash": "f357ab0bd3f2e9a77857a05a6282c0228bf96fa749c2411fb44b0c94de09cecc"
  },
  "gap": {
    "id": 1,
    "status": "pending_confirmation",
    "workflow_stage": "awaiting_human_confirmation",
    "paper_set_id": 2,
    "explanation_version": 2,
    "not_novelty_proof": true
  },
  "human_confirmation": "not_performed",
  "plan": null
}
```

### ruff — BLOCKED

```text
ruff executable is unavailable
```

### mypy — BLOCKED

```text
mypy executable is unavailable
```

### frontend_syntax_transpile — PASS

```text
{
  "status": "PASS",
  "fileCount": 32,
  "typescriptVersion": "5.8.3",
  "scope": "syntax transpile only; not dependency-aware typecheck or production build"
}
```

### frontend_typecheck — BLOCKED

```text
apps/web/node_modules is absent and dependency installation cannot be completed in the current offline/DNS-constrained environment
```

### frontend_unit_tests — BLOCKED

```text
apps/web/node_modules is absent and dependency installation cannot be completed in the current offline/DNS-constrained environment
```

### frontend_build — BLOCKED

```text
apps/web/node_modules is absent and dependency installation cannot be completed in the current offline/DNS-constrained environment
```

### playwright_e2e — BLOCKED

```text
apps/web/node_modules is absent and dependency installation cannot be completed in the current offline/DNS-constrained environment
```

### docker_compose_config — BLOCKED

```text
docker executable is unavailable
```

### docker_cold_start — BLOCKED

```text
docker executable is unavailable
```

### mcp_sdk_import — BLOCKED

```text
Traceback (most recent call last):
  File "<string>", line 1, in <module>
    import mcp; print('official MCP SDK import PASS')
    ^^^^^^^^^^
ModuleNotFoundError: No module named 'mcp'
```

### mcp_stdio — BLOCKED

```text
official MCP SDK is unavailable
```

### live_open_sources — BLOCKED

```text
live network smoke was not requested; deterministic regression uses fixture sources
```

### licensed_sources — SKIPPED

```text
licensed adapters are outside the implemented source set and no lawful credentials were supplied
```

### uv_lock_check — PASS

```text
Resolved 70 packages in 1ms
```

## Claim boundary

- Candidate research gaps and Gap Explanation Agent outputs are evidence-bounded hypotheses, not proof of novelty.
- simulated_human_confirmation is an automated acceptance action and is never reported as expert review.
- Fixture papers are deterministic offline test records, not scholarly evidence.
- Live source smoke is non-deterministic: retain query/time/source status/stable identifiers/raw response hashes rather than fixed titles or counts.
- Abstract-only analysis does not support full-text experimental protocol, Future Work, or author-stated limitation claims.
- Field citation locations currently preserve supplied page/chunk provenance; they are not sentence-level entailment proof.
- Search diversity is seeded within relevance bands and remains reproducible per saved session; it is not unrestricted randomization.
- The package is a local/LAN research workflow implementation, not a verified public SaaS deployment.
