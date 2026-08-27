from pathlib import Path

from fastapi.testclient import TestClient
from scripts.run_acceptance_scenario import run_scenario

from research_navigator.config import Settings
from research_navigator.main import create_app


def settings_for(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "state"
    return Settings(
        data_dir=data_dir,
        database_url=f"sqlite+pysqlite:///{(data_dir / 'scenario.db').as_posix()}",
        upload_dir=data_dir / "uploads",
        vector_dir=data_dir / "vectors",
        backup_dir=data_dir / "backups",
        allowed_origins=("http://localhost:5173",),
        enable_fixture_source=True,
        enable_openalex=False,
        enable_crossref=False,
        enable_arxiv=False,
        enable_semantic_scholar=False,
        semantic_scholar_api_key=None,
        unpaywall_email=None,
        crossref_mailto=None,
        llm_base_url=None,
        llm_api_key=None,
        llm_model=None,
        max_pdf_bytes=2_000_000,
        session_ttl_hours=24,
        environment="test",
    )


def test_http_first_acceptance_scenario_stops_before_real_human_confirmation(
    tmp_path: Path,
) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        report = run_scenario(
            client, scenario_version="feedback-closure-v1", confirm_demo_gap=False
        )
    assert report["execution_mode"] == "http_api_only_after_bootstrap"
    assert report["search"]["requested_limit"] == 50
    assert report["paper_set"]["paper_ids"]
    assert report["comparison"]["row_count"] >= 10
    assert report["gap"]["workflow_stage"] == "awaiting_human_confirmation"
    assert report["human_confirmation"] == "not_performed"
    assert report["plan"] is None


def test_acceptance_scenario_source_has_no_direct_orm_mutation() -> None:
    source = (Path(__file__).parents[2] / "scripts" / "run_acceptance_scenario.py").read_text(
        encoding="utf-8"
    )
    forbidden = [
        "research_navigator.models",
        "sqlalchemy.orm",
        ".state.database",
        "session.add(",
        "session.commit(",
    ]
    assert not [token for token in forbidden if token in source]
