from datetime import UTC, datetime
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


def test_plan_output_migration_preserves_user_edited_history(tmp_path, monkeypatch):
    monkeypatch.delenv("RN_DATABASE_URL", raising=False)
    database_path = tmp_path / "historic-plan.db"
    config = alembic_config(database_path)
    command.upgrade(config, "0005")
    engine = sa.create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    metadata = sa.MetaData()
    metadata.reflect(engine)
    stamp = datetime.now(UTC)
    common = {"created_at": stamp, "updated_at": stamp}
    with engine.begin() as connection:
        connection.execute(metadata.tables["users"].insert().values(
            id=1, email="migration@example.invalid", password_hash="NOT-A-CREDENTIAL",
            display_name="历史测试", is_admin=False, is_active=True, **common,
        ))
        connection.execute(metadata.tables["research_projects"].insert().values(
            id=1, user_id=1, name="local historic fixture", status="active", **common,
        ))
        connection.execute(metadata.tables["research_plans"].insert().values(
            id=1, user_id=1, project_id=1, title="用户编辑计划", objective="保留原意",
            status="active", **common,
        ))
        connection.execute(metadata.tables["plan_items"].insert().values(
            id=1, plan_id=1, user_id=1, category="risk_check", title="用户步骤",
            description="用户已编辑的内容", notes="不是复现证明", sequence=1,
            status="done", **common,
        ))
    command.upgrade(config, "head")
    # New connection/reflection: no stale ORM metadata or auto-backfilled history.
    current = sa.Table("plan_items", sa.MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        row = connection.execute(sa.select(current)).mappings().one()
        assert row["description"] == "用户已编辑的内容"
        assert row["notes"] == "不是复现证明"
        assert row["status"] == "done"
        assert row["purpose"] is None
        assert row["expected_output"] is None
    engine.dispose()


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
