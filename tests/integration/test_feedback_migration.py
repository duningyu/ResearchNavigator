from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import inspect

from alembic import command

ROOT = Path(__file__).resolve().parents[2]


def alembic_config(database_path: Path) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path.as_posix()}")
    return config


def test_upgrade_existing_0002_database_to_feedback_closure_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "upgrade.db"
    config = alembic_config(database_path)
    command.upgrade(config, "0002")
    command.upgrade(config, "head")

    inspector = inspect(sa.create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}"))
    tables = set(inspector.get_table_names())
    assert {
        "paper_sets",
        "paper_set_items",
        "comparison_runs",
        "gap_explanations",
        "user_settings",
        "idempotency_records",
    } <= tables
    search_columns = {item["name"] for item in inspector.get_columns("search_sessions")}
    assert {
        "search_mode",
        "ranking_rule_version",
        "diversity_seed",
        "composition_json",
    } <= search_columns
    gap_columns = {item["name"] for item in inspector.get_columns("gap_candidates")}
    assert {"paper_set_id", "direction_snapshot_json"} <= gap_columns
