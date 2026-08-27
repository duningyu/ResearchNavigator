# ResearchNavigator 2.2.0 deployment report

- Docker acceptance harness implementation: PASS (3 contract tests).
- Actual Docker cold build/restart/down-up/backup-restore execution: BLOCKED; `docker` is unavailable.
- SQLite backup/restore integration tests: PASS (4 tests).
- Alembic 0001→0005 and SQLite integrity: PASS (53 tables, `ok`).
- No production/LAN deployment claim is made from these results.

Evidence: `codex_audit/runs/20260827T191732Z_RN220_FINAL/logs/docker_harness_contract.log`, `codex_audit/runs/20260827T191732Z_RN220_FINAL/logs/docker_persistence_blocked.json`, `codex_audit/runs/20260827T191732Z_RN220_FINAL/logs/backup_restore.log`, `codex_audit/runs/20260827T191732Z_RN220_FINAL/logs/alembic_upgrade_0005.log`.
