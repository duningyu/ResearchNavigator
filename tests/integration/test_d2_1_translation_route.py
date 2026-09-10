from pathlib import Path

from fastapi.testclient import TestClient

from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.models import Paper
from research_navigator.translation.service import TranslationDraft, TranslationService


class CountingAdapter:
    def __init__(self, draft: TranslationDraft | dict[str, object] | Exception) -> None:
        self.draft = draft
        self.calls = 0

    def translate(self, text: str, target_language: str) -> TranslationDraft | dict[str, object]:
        self.calls += 1
        if isinstance(self.draft, Exception):
            raise self.draft
        return self.draft


def _settings(tmp_path: Path) -> Settings:
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


def _seed_paper(app, abstract: str) -> int:
    with app.state.database.session_factory() as session:
        paper = Paper(title="Route fixture", normalized_title="route fixture", abstract=abstract)
        session.add(paper)
        session.commit()
        session.refresh(paper)
        return paper.id


def _auth_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "research-pass-123", "display_name": "route-test"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_translation_route_uses_real_app_and_process_cache(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    adapter = CountingAdapter(TranslationDraft("稳定译文"))
    with TestClient(app) as client:
        app.state.translation_service = TranslationService(adapter, pipeline_version="route-v1")
        headers = _auth_headers(client, "translation-route@example.com")
        paper_id = _seed_paper(app, "A 5% increase is not guaranteed.")

        first = client.get(
            f"/api/papers/{paper_id}/abstract-translation?target_language=zh-CN",
            headers=headers,
        )
        second = client.get(
            f"/api/papers/{paper_id}/abstract-translation?target_language=zh-CN",
            headers=headers,
        )

        assert first.status_code == 200
        assert first.json()["translated_abstract"] == "稳定译文"
        assert first.json()["original_abstract"] == "A 5% increase is not guaranteed."
        assert second.json()["cache_hit"] is True
        assert adapter.calls == 1

        with app.state.database.session_factory() as session:
            paper = session.get(Paper, paper_id)
            assert paper is not None
            paper.abstract = "A 10% increase remains uncertain."
            session.commit()

        changed = client.get(
            f"/api/papers/{paper_id}/abstract-translation?target_language=zh-CN",
            headers=headers,
        )
        assert changed.status_code == 200
        assert adapter.calls == 2


def test_translation_route_preserves_failure_contracts(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        headers = _auth_headers(client, "translation-failure@example.com")
        paper_id = _seed_paper(app, "source")

        app.state.translation_service = TranslationService(
            CountingAdapter(RuntimeError("stub failure")), pipeline_version="route-v1"
        )
        failed = client.get(f"/api/papers/{paper_id}/abstract-translation", headers=headers)
        assert failed.status_code == 200
        assert failed.json()["status"] == "failed"
        assert failed.json()["translated_abstract"] is None

        app.state.translation_service = TranslationService(
            CountingAdapter({"text": "片段", "complete": False}), pipeline_version="route-v1"
        )
        partial = client.get(f"/api/papers/{paper_id}/abstract-translation", headers=headers)
        assert partial.json()["status"] == "partial"
        assert partial.json()["translated_abstract"] is None
