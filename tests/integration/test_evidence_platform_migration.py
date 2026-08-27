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


def test_upgrade_0004_to_evidence_platform_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "evidence-platform.db"
    config = alembic_config(database_path)
    command.upgrade(config, "0004")
    command.upgrade(config, "head")

    inspector = inspect(sa.create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}"))
    tables = set(inspector.get_table_names())
    assert {
        "source_runtime_states",
        "authors",
        "paper_authors",
        "author_source_records",
        "dataset_cards",
        "paper_dataset_mentions",
        "direction_cluster_runs",
        "direction_clusters",
        "direction_cluster_members",
        "evaluation_studies",
        "evaluation_tasks",
        "evaluation_assignments",
        "evaluation_ratings",
        "evaluation_results",
    } <= tables

    document_columns = {item["name"] for item in inspector.get_columns("paper_documents")}
    assert {
        "source_url",
        "source_record_id",
        "rights_basis",
        "license",
        "retrieved_at",
        "response_hash",
        "acquisition_run_id",
        "parse_status",
    } <= document_columns

    analysis_columns = {item["name"] for item in inspector.get_columns("paper_analyses")}
    assert {
        "analysis_run_id",
        "analysis_mode",
        "provider",
        "model_name",
        "prompt_version",
        "input_evidence_hash",
        "provider_output_hash",
        "fallback_reason",
    } <= analysis_columns

    tool_columns = {item["name"] for item in inspector.get_columns("tool_calls")}
    assert {
        "latency_ms",
        "attempt_count",
        "token_usage_json",
        "response_status",
        "validated_output_hash",
    } <= tool_columns
