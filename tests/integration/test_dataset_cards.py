from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from research_navigator.analysis.structured import CitationLocator, PaperAnalysisOutput
from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.models import Paper, PaperAnalysisRecord, User


def settings_for(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "state"
    return Settings(
        data_dir=data_dir,
        database_url=f"sqlite+pysqlite:///{(data_dir / 'test.db').as_posix()}",
        upload_dir=data_dir / "uploads",
        vector_dir=data_dir / "vectors",
        backup_dir=data_dir / "backups",
        allowed_origins=("http://localhost:5173",),
        enable_fixture_source=False,
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


def register(client: TestClient) -> tuple[dict[str, str], int]:
    data = client.post(
        "/api/auth/register",
        json={"email": "datasets@example.com", "password": "research-pass-123", "display_name": "D"},
    ).json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data["user"]["id"]


def seed_analysis(app, user_id: int, *, evidence_level: str) -> tuple[int, int]:
    citation = CitationLocator(
        source_type="open_access_repository" if evidence_level == "open_fulltext" else "abstract",
        section="Experiments" if evidence_level == "open_fulltext" else "Abstract",
        page_start=4 if evidence_level == "open_fulltext" else None,
        page_end=4 if evidence_level == "open_fulltext" else None,
        chunk_id=10 if evidence_level == "open_fulltext" else None,
    )
    analysis = PaperAnalysisOutput(
        paper_id=0,
        evidence_level=evidence_level,
        executive_summary="Dataset evidence.",
        summary="Dataset evidence.",
        datasets=["SWaT"],
        metrics=["PR-AUC"],
        experimental_protocol=["The training split uses 80 percent and the test split uses 20 percent."],
        experiment_design=["The training split uses 80 percent and the test split uses 20 percent."],
        field_states={"datasets": "evidenced", "metrics": "evidenced", "experimental_protocol": "evidenced"},
        field_citations={"datasets": [citation], "metrics": [citation], "experimental_protocol": [citation]},
    )
    with app.state.database.session() as session:
        paper = Paper(title="Dataset Paper", normalized_title="dataset paper")
        session.add(paper)
        session.flush()
        analysis.paper_id = paper.id
        row = PaperAnalysisRecord(
            user_id=user_id,
            paper_id=paper.id,
            evidence_level=evidence_level,
            analysis_version=analysis.analysis_version,
            analysis_json=analysis.model_dump_json(),
            direction_similarity_json="{}",
            reproduction_assessment_json="{}",
        )
        session.add(row)
        session.commit()
        return paper.id, row.id


def test_dataset_card_is_evidence_bounded_and_user_scoped(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers, user_id = register(client)
        paper_id, _ = seed_analysis(app, user_id, evidence_level="abstract_only")
        refreshed = client.post(f"/api/papers/{paper_id}/datasets/refresh", headers=headers)
        assert refreshed.status_code == 200, refreshed.text
        card = refreshed.json()[0]
        assert card["canonical_name"] == "SWaT"
        assert card["identity_status"] == "mentioned_only"
        assert card["license"] is None
        assert card["access_url"] is None
        assert card["train_split"] is None
        assert card["test_split"] is None
        assert card["metrics"] == ["PR-AUC"]
        assert card["field_citations"]["datasets"][0]["source_type"] == "abstract"

        other = client.post(
            "/api/auth/register",
            json={"email": "datasets-other@example.com", "password": "research-pass-123", "display_name": "O"},
        ).json()
        other_headers = {"Authorization": f"Bearer {other['access_token']}"}
        assert client.get(f"/api/datasets/{card['id']}", headers=other_headers).status_code == 404


def test_fulltext_dataset_card_can_show_explicit_split_evidence(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers, user_id = register(client)
        paper_id, _ = seed_analysis(app, user_id, evidence_level="open_fulltext")
        card = client.post(f"/api/papers/{paper_id}/datasets/refresh", headers=headers).json()[0]
        assert "training split" in card["train_split"].lower()
        assert "test split" in card["test_split"].lower()
