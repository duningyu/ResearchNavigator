from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen.canvas import Canvas

from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.models import Paper


def bind_local_test_paper(client: TestClient, paper_id: int) -> None:
    # Independent local metadata fixture; upload must itself carry the matching version.
    with client.app.state.database.session() as session:
        paper = session.get(Paper, paper_id)
        assert paper is not None
        paper.arxiv_id = "2401.12345v2"
        session.commit()


def make_pdf(*, partial: bool = False) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(72, 810, "arXiv:2401.12345v2")
    canvas.drawString(72, 760, "Abstract")
    canvas.drawString(72, 735, "We predict future horizon anomaly risk for industrial time series.")
    canvas.drawString(72, 710, "Method")
    canvas.drawString(72, 685, "The method ranks alerts under a fixed budget with causal windows.")
    if partial:
        canvas.showPage()
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def settings_for(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "state"
    return Settings(
        data_dir=data_dir,
        database_url=f"sqlite+pysqlite:///{(data_dir / 'test.db').as_posix()}",
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


@pytest.mark.parametrize("partial", [False, True])
def test_user_uploaded_pdf_is_persisted_chunked_and_retrievable(
    tmp_path: Path, partial: bool
) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        auth = client.post(
            "/api/auth/register",
            json={
                "email": "pdf@example.com",
                "password": "research-pass-123",
                "display_name": "PDF User",
            },
        ).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        paper_id = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "future horizon", "sources": ["fixture"], "limit": 1},
        ).json()["papers"][0]["id"]

        bind_local_test_paper(client, paper_id)
        upload = client.post(
            f"/api/papers/{paper_id}/upload",
            headers=headers,
            data={"rights_confirmed": "true"},
            files={"file": ("authorized-paper.pdf", make_pdf(partial=partial), "application/pdf")},
        )
        assert upload.status_code == 201, upload.text
        expected_level = "partial_fulltext" if partial else "user_uploaded_fulltext"
        assert upload.json()["evidence_level"] == expected_level
        assert upload.json()["page_count"] == (2 if partial else 1)
        assert upload.json()["chunk_count"] >= 1

        status = client.get(f"/api/papers/{paper_id}/content-status", headers=headers)
        assert status.status_code == 200
        assert status.json()["evidence_level"] == expected_level

        retrieval = client.post(
            f"/api/papers/{paper_id}/retrieve",
            headers=headers,
            json={"query": "future horizon anomaly risk", "top_k": 3},
        )
        assert retrieval.status_code == 200, retrieval.text
        assert retrieval.json()["hits"]
        first = retrieval.json()["hits"][0]
        assert "future horizon" in first["text"].lower()
        assert first["citation"]["page_start"] == 1
        assert first["citation"]["chunk_id"]


def make_evidence_rich_pdf() -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer)
    lines = [
        "arXiv:2401.12345v2",
        "Abstract",
        "We study future-window anomaly risk prediction for industrial time series.",
        "Method",
        "We propose a Temporal Convolutional Network with Pairwise Ranking "
        "for alert prioritization.",
        "The pipeline first encodes historical windows and then ranks future risk.",
        "Dataset",
        "Experiments use SWaT and SMD datasets.",
        "Metrics",
        "We evaluate PR-AUC, Precision, Recall and F1.",
        "Results",
        "The proposed method improves PR-AUC over baselines in our experiments.",
        "Limitations",
        "A limitation is evaluation on a limited set of industrial datasets.",
        "Future Work",
        "Future work will evaluate cross-device generalization and additional datasets.",
    ]
    y = 790
    for line in lines:
        canvas.drawString(60, y, line)
        y -= 32
    canvas.save()
    return buffer.getvalue()


def test_fulltext_analysis_extracts_evidence_fields_with_page_chunk_citations(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        auth = client.post(
            "/api/auth/register",
            json={
                "email": "rich-pdf@example.com",
                "password": "research-pass-123",
                "display_name": "Rich PDF",
            },
        ).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        paper_id = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "future horizon", "sources": ["fixture"], "limit": 1},
        ).json()["papers"][0]["id"]
        bind_local_test_paper(client, paper_id)
        upload = client.post(
            f"/api/papers/{paper_id}/upload",
            headers=headers,
            data={"rights_confirmed": "true"},
            files={"file": ("evidence-rich.pdf", make_evidence_rich_pdf(), "application/pdf")},
        )
        assert upload.status_code == 201, upload.text

        analyzed = client.post(f"/api/papers/{paper_id}/analyze", headers=headers, json={})
        assert analyzed.status_code == 200, analyzed.text
        analysis = analyzed.json()["analysis"]
        assert analysis["evidence_level"] == "user_uploaded_fulltext"
        assert "Temporal Convolutional Network" in analysis["core_methods"]
        assert "Pairwise Ranking" in analysis["core_methods"]
        assert "SWaT" in analysis["datasets"]
        assert "PR-AUC" in analysis["metrics"]
        assert analysis["future_work_explicit"]
        assert analysis["limitations_author_stated"]
        assert analysis["research_route"]
        assert analysis["field_states"]["future_work_explicit"] == "evidenced"
        citations = analysis["field_citations"]["future_work_explicit"]
        assert citations
        assert citations[0]["page_start"] == 1
        assert citations[0]["chunk_id"]


def test_document_list_delete_and_retrieve_are_user_scoped(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        first = client.post(
            "/api/auth/register",
            json={
                "email": "docs-a@example.com",
                "password": "research-pass-123",
                "display_name": "A",
            },
        ).json()
        second = client.post(
            "/api/auth/register",
            json={
                "email": "docs-b@example.com",
                "password": "research-pass-123",
                "display_name": "B",
            },
        ).json()
        first_headers = {"Authorization": f"Bearer {first['access_token']}"}
        second_headers = {"Authorization": f"Bearer {second['access_token']}"}
        paper_id = client.post(
            "/api/search/papers",
            headers=first_headers,
            json={"query": "future horizon", "sources": ["fixture"], "limit": 1},
        ).json()["papers"][0]["id"]
        upload = client.post(
            f"/api/papers/{paper_id}/upload",
            headers=first_headers,
            data={"rights_confirmed": "true"},
            files={"file": ("owned.pdf", make_pdf(), "application/pdf")},
        )
        document_id = upload.json()["id"]

        listed = client.get(f"/api/papers/{paper_id}/documents", headers=first_headers)
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [document_id]
        other_list = client.get(f"/api/papers/{paper_id}/documents", headers=second_headers)
        assert other_list.status_code == 200
        assert other_list.json() == []
        denied_delete = client.delete(f"/api/documents/{document_id}", headers=second_headers)
        assert denied_delete.status_code == 404
        deleted = client.delete(f"/api/documents/{document_id}", headers=first_headers)
        assert deleted.status_code == 204
        retrieval = client.post(
            f"/api/papers/{paper_id}/retrieve",
            headers=first_headers,
            json={"query": "future horizon", "top_k": 3},
        )
        assert retrieval.status_code == 200
        assert retrieval.json()["hits"] == []
