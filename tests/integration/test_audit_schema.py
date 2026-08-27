from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import inspect

from alembic import command

ROOT = Path(__file__).resolve().parents[2]


def test_minimum_audit_schema_is_migrated(tmp_path: Path) -> None:
    database_path = tmp_path / "audit.db"
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path.as_posix()}")
    command.upgrade(config, "head")
    engine = sa.create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"agent_runs", "tool_calls", "prompt_versions", "source_requests"} <= tables

    agent_columns = {column["name"] for column in inspector.get_columns("agent_runs")}
    assert {
        "run_id",
        "user_id",
        "project_id",
        "workflow_version",
        "prompt_version",
        "model_provider",
        "model_name",
        "started_at",
        "finished_at",
        "status",
        "error",
        "output_hash",
    } <= agent_columns

    tool_columns = {column["name"] for column in inspector.get_columns("tool_calls")}
    assert {"run_id", "user_id", "tool_name", "input_json", "output_json", "status"} <= tool_columns

    source_columns = {column["name"] for column in inspector.get_columns("source_requests")}
    assert {
        "run_id",
        "user_id",
        "project_id",
        "query",
        "source_records_json",
        "status",
    } <= source_columns
    engine.dispose()
