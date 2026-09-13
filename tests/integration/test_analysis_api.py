from pathlib import Path

from fastapi.testclient import TestClient

from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.scholarly.base import (
    AdapterSearchResult,
    PaperRecord,
    ScholarlyAdapter,
    SearchRequest,
    SourceProvenance,
    SourceStatus,
)
from research_navigator.scholarly.service import FederatedSearchService


class VerifiedAbstractAdapter(ScholarlyAdapter):
    name = "verified"

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        provenance = SourceProvenance(
            source=self.name,
            source_id="10.1000/verified-analysis",
            source_url="https://example.test/verified-analysis",
            raw_hash="f" * 64,
        )
        abstract = (
            "We propose an Anomaly Transformer for multivariate time-series anomaly "
            "detection and future alert ranking. Experiments report precision and recall."
        )
        return AdapterSearchResult(
            records=[
                PaperRecord(
                    title="Verified anomaly transformer analysis",
                    abstract=abstract,
                    publication_year=2026,
                    doi="10.1000/verified-analysis",
                    source_provenance=[provenance],
                    abstract_provenance=provenance,
                )
            ],
            status=SourceStatus(status="ok", result_count=1),
        )


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


def test_abstract_analysis_is_structured_scored_and_persisted(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        app.state.search_service = FederatedSearchService([VerifiedAbstractAdapter()])
        auth = client.post(
            "/api/auth/register",
            json={
                "email": "analysis@example.com",
                "password": "research-pass-123",
                "display_name": "Analysis User",
            },
        ).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        client.put(
            "/api/research-profiles/me",
            headers=headers,
            json={
                "stage": "硕士一年级",
                "major": "大数据技术与工程",
                "broad_direction": "多变量时序异常检测",
                "keywords": ["future horizon", "alert ranking", "transformer"],
                "excluded_terms": ["image segmentation"],
                "preferences": ["复现优先"],
                "compute_constraints": "单卡 GPU",
            },
        )
        paper_id = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "anomaly transformer", "sources": ["verified"], "limit": 1},
        ).json()["papers"][0]["id"]

        analyzed = client.post(f"/api/papers/{paper_id}/analyze", headers=headers, json={})
        assert analyzed.status_code == 200, analyzed.text
        payload = analyzed.json()
        assert payload["analysis"]["evidence_level"] == "abstract_only"
        assert payload["analysis"]["future_work_explicit"] == []
        assert 0 <= payload["direction_similarity"]["score"] <= 100
        reproduction = payload["reproduction_assessment"]
        assert reproduction["score"] is None
        assert reproduction["evidence_coverage"] is not None
        assert reproduction["dimensions"]
        assert reproduction["recommended_first_step"]

        stored = client.get(f"/api/papers/{paper_id}/analysis", headers=headers)
        assert stored.status_code == 200
        assert stored.json()["analysis_version"] == payload["analysis_version"]

        project = client.post(
            "/api/projects", headers=headers, json={"name": "Isolated direction"}
        ).json()
        scoped = client.post(
            f"/api/papers/{paper_id}/analyze", headers=headers,
            json={"project_id": project["id"]},
        )
        assert scoped.status_code == 200
        unscoped = client.get(f"/api/papers/{paper_id}/analysis", headers=headers).json()
        assert unscoped["id"] == payload["id"]
        assert client.get(
            f"/api/papers/{paper_id}/analysis?project_id={project['id']}", headers=headers,
        ).json()["id"] == scoped.json()["id"]


def test_abstract_only_analysis_marks_unsupported_fields_as_insufficient_evidence(
    tmp_path: Path,
) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        app.state.search_service = FederatedSearchService([VerifiedAbstractAdapter()])
        auth = client.post(
            "/api/auth/register",
            json={
                "email": "analysis-boundary@example.com",
                "password": "research-pass-123",
                "display_name": "Boundary",
            },
        ).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        paper_id = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "anomaly transformer", "sources": ["verified"], "limit": 1},
        ).json()["papers"][0]["id"]

        response = client.post(f"/api/papers/{paper_id}/analyze", headers=headers, json={})
        assert response.status_code == 200, response.text
        analysis = response.json()["analysis"]
        assert analysis["executive_summary"]
        assert analysis["core_methods"]
        assert analysis["field_states"]["experimental_protocol"] == "insufficient_evidence"
        assert analysis["field_states"]["future_work_explicit"] == "insufficient_evidence"
        assert analysis["field_states"]["limitations_author_stated"] == "insufficient_evidence"
        assert "摘要级证据不足" in analysis["warnings"]
        assert analysis["experimental_protocol"] == []
        assert analysis["field_citations"]["executive_summary"]
