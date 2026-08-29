from __future__ import annotations

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

TARGET_DOI = "10.1177/20552076241297729"


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


def record(doi: str, title: str) -> PaperRecord:
    provenance = SourceProvenance(
        source="stub",
        source_id=doi,
        source_url=f"https://example.test/{doi}",
        raw_hash="a" * 64,
    )
    return PaperRecord(title=title, doi=doi, source_provenance=[provenance])


class ExactStubAdapter(ScholarlyAdapter):
    def __init__(self, name: str, exact: PaperRecord | None, broad: list[PaperRecord]) -> None:
        self.name = name
        self.exact = exact
        self.broad = broad
        self.calls: list[str] = []

    async def resolve_exact(self, doi: str) -> PaperRecord | None:
        self.calls.append(f"exact:{doi}")
        return self.exact if self.exact and self.exact.doi == doi else None

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        self.calls.append(f"search:{request.query}")
        return AdapterSearchResult(
            records=self.broad,
            status=SourceStatus(status="ok", result_count=len(self.broad)),
        )


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "exact-doi@example.com",
            "password": "research-pass-123",
            "display_name": "Exact DOI",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_resolve_doi_uses_exact_identifier_before_broad_search(tmp_path: Path) -> None:
    target = record(TARGET_DOI, "Digital health implementation in Australia")
    unrelated = record("10.0000/unrelated", "Unrelated broad-search result")
    adapter = ExactStubAdapter("stub", target, [unrelated])
    app = create_app(settings_for(tmp_path))

    with TestClient(app) as client:
        app.state.search_service = FederatedSearchService([adapter])
        resolved = client.post(
            "/api/papers/resolve",
            headers=auth_headers(client),
            json={"doi": TARGET_DOI, "sources": ["stub"]},
        )

    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["doi"] == TARGET_DOI
    assert adapter.calls == [f"exact:{TARGET_DOI}"]


def test_resolve_doi_falls_back_to_next_exact_provider(tmp_path: Path) -> None:
    target = record(TARGET_DOI, "Digital health implementation in Australia")
    first = ExactStubAdapter("first", None, [record("10.0000/a", "Wrong")])
    second = ExactStubAdapter("second", target, [record("10.0000/b", "Wrong")])
    app = create_app(settings_for(tmp_path))

    with TestClient(app) as client:
        app.state.search_service = FederatedSearchService([first, second])
        resolved = client.post(
            "/api/papers/resolve",
            headers=auth_headers(client),
            json={"doi": TARGET_DOI, "sources": ["first", "second"]},
        )

    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["doi"] == TARGET_DOI
    assert first.calls == [f"exact:{TARGET_DOI}"]
    assert second.calls == [f"exact:{TARGET_DOI}"]


def test_resolve_unknown_doi_does_not_return_broad_similar_paper(tmp_path: Path) -> None:
    adapter = ExactStubAdapter("stub", None, [record("10.0000/unrelated", "Similar title")])
    app = create_app(settings_for(tmp_path))

    with TestClient(app) as client:
        app.state.search_service = FederatedSearchService([adapter])
        response = client.post(
            "/api/papers/resolve",
            headers=auth_headers(client),
            json={"doi": "10.1177/does-not-exist", "sources": ["stub"]},
        )

    assert response.status_code == 404
    assert adapter.calls == ["exact:10.1177/does-not-exist"]


def test_text_resolution_still_uses_broad_search(tmp_path: Path) -> None:
    target = record("10.0000/text", "attention")
    adapter = ExactStubAdapter("stub", None, [target])
    app = create_app(settings_for(tmp_path))

    with TestClient(app) as client:
        app.state.search_service = FederatedSearchService([adapter])
        response = client.post(
            "/api/papers/resolve",
            headers=auth_headers(client),
            json={"title": "attention", "sources": ["stub"]},
        )

    assert response.status_code == 200, response.text
    assert response.json()["doi"] == "10.0000/text"
    assert adapter.calls == ["search:attention"]
