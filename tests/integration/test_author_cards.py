from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from research_navigator.authors.service import refresh_author_cards
from research_navigator.config import Settings
from research_navigator.main import create_app
from research_navigator.models import Author, Paper, PaperAuthorLink, PaperSource, User


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


def register(client: TestClient) -> dict[str, str]:
    data = client.post(
        "/api/auth/register",
        json={"email": "authors@example.com", "password": "research-pass-123", "display_name": "A"},
    ).json()
    return {"Authorization": f"Bearer {data['access_token']}"}


def seed(app) -> tuple[int, int]:
    with app.state.database.session() as session:
        papers = []
        for index in range(2):
            paper = Paper(
                title=f"Author Paper {index}",
                normalized_title=f"author paper {index}",
                authors_json=json.dumps(
                    [
                        {
                            "name": "Jane Doe",
                            "orcid": "0000-0002-1825-0097",
                            "affiliations": ["Research Lab"],
                            "source_author_id": "A1",
                        },
                        {
                            "name": "Wei Zhang",
                            "orcid": None,
                            "affiliations": [],
                            "source_author_id": None,
                        },
                    ]
                ),
            )
            session.add(paper)
            session.flush()
            session.add(
                PaperSource(
                    paper_id=paper.id,
                    source="openalex",
                    source_id=f"W{index}",
                    source_url=f"https://openalex.org/W{index}",
                    raw_hash=str(index) * 64,
                    is_fixture=False,
                )
            )
            papers.append(paper.id)
        session.commit()
        return papers[0], papers[1]


def test_refresh_merges_orcid_but_never_name_only_and_api_exposes_provenance(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = register(client)
        p1, p2 = seed(app)
        with app.state.database.session() as session:
            refresh_author_cards(session, session.get(Paper, p1))
            refresh_author_cards(session, session.get(Paper, p2))
            session.commit()
            assert session.scalar(select(func.count(Author.id))) == 3
            jane_ids = list(session.scalars(select(Author.id).where(Author.orcid.is_not(None))))
            assert len(jane_ids) == 1
            unresolved = list(
                session.scalars(select(Author).where(Author.identity_status == "unresolved"))
            )
            assert len(unresolved) == 2

        response = client.post(f"/api/papers/{p1}/authors/refresh", headers=headers)
        assert response.status_code == 200, response.text
        cards = client.get(f"/api/papers/{p1}/authors", headers=headers).json()
        assert len(cards) == 2
        jane = next(item for item in cards if item["canonical_name"] == "Jane Doe")
        assert jane["identity_status"] == "resolved"
        assert jane["orcid"] == "0000-0002-1825-0097"
        assert jane["affiliations"] == ["Research Lab"]
        assert jane["provenance"]
        wei = next(item for item in cards if item["canonical_name"] == "Wei Zhang")
        assert wei["identity_status"] == "unresolved"
        assert wei["works_count"] is None
