from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import inspect

from alembic import command
from research_navigator.models import Base

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TABLES = {
    "agent_runs",
    "favorites",
    "gap_candidates",
    "gap_evidence",
    "job_events",
    "jobs",
    "notes",
    "paper_analyses",
    "paper_chunks",
    "paper_documents",
    "paper_sources",
    "paper_tags",
    "papers",
    "plan_items",
    "reading_status",
    "recommendations",
    "research_plans",
    "research_profiles",
    "research_projects",
    "search_sessions",
    "session_tokens",
    "tags",
    "users",
}


def alembic_config(database_path: Path) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path.as_posix()}")
    return config


def test_empty_database_upgrade_has_frozen_schema_constraints_indexes_and_fts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("RN_DATABASE_URL", raising=False)
    database_path = tmp_path / "migration.db"
    config = alembic_config(database_path)

    command.upgrade(config, "head")

    engine = sa.create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert tables >= EXPECTED_TABLES
    assert "paper_chunks_fts" in tables
    assert "ix_jobs_status_created" in {item["name"] for item in inspector.get_indexes("jobs")}
    assert "ix_paper_chunks_access" in {
        item["name"] for item in inspector.get_indexes("paper_chunks")
    }
    assert "provides_abstract" in {
        item["name"] for item in inspector.get_columns("paper_sources")
    }
    note_foreign_keys = {
        (tuple(item["constrained_columns"]), item["referred_table"])
        for item in inspector.get_foreign_keys("notes")
    }
    assert (("user_id",), "users") in note_foreign_keys
    assert (("paper_id",), "papers") in note_foreign_keys
    engine.dispose()


def test_downgrade_base_removes_schema_and_upgrade_recreates_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("RN_DATABASE_URL", raising=False)
    database_path = tmp_path / "roundtrip.db"
    config = alembic_config(database_path)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = sa.create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    downgraded_tables = set(inspect(engine).get_table_names())
    assert not EXPECTED_TABLES & downgraded_tables
    assert "paper_chunks_fts" not in downgraded_tables
    engine.dispose()

    command.upgrade(config, "head")
    engine = sa.create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    assert set(inspect(engine).get_table_names()) >= EXPECTED_TABLES
    assert "paper_chunks_fts" in inspect(engine).get_table_names()
    engine.dispose()


def test_historical_migration_ignores_tables_added_to_runtime_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("RN_DATABASE_URL", raising=False)
    sentinel = sa.Table(
        "future_runtime_only_table",
        Base.metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    try:
        database_path = tmp_path / "frozen.db"
        command.upgrade(alembic_config(database_path), "head")
        engine = sa.create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
        assert "future_runtime_only_table" not in inspect(engine).get_table_names()
        engine.dispose()
    finally:
        Base.metadata.remove(sentinel)
