from pathlib import Path

from fastapi.testclient import TestClient
from tests.integration.test_auth_projects import auth_header, make_client, register


def _fixture_papers(client: TestClient, headers: dict[str, str]) -> list[dict[str, object]]:
    response = client.post(
        "/api/search/papers",
        headers=headers,
        json={"query": "anomaly detection", "sources": ["fixture"], "limit": 20},
    )
    assert response.status_code == 200, response.text
    return response.json()["papers"]


def test_paper_set_persists_explicit_ordered_selection(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        owner = register(client, "paper-set@example.com")
        headers = auth_header(owner)
        project = client.post(
            "/api/projects",
            headers=headers,
            json={"name": "Explicit corpus", "description": None, "broad_direction": "TSAD"},
        ).json()
        papers = _fixture_papers(client, headers)
        selected = [int(papers[1]["id"]), int(papers[0]["id"])]

        created = client.post(
            "/api/paper-sets",
            headers=headers,
            json={
                "project_id": project["id"],
                "purpose": "compare",
                "name": "Chosen papers",
                "paper_ids": selected,
            },
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["paper_ids"] == selected
        assert [paper["id"] for paper in payload["papers"]] == selected
        assert payload["purpose"] == "compare"

        listed = client.get("/api/paper-sets", headers=headers)
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == payload["id"]


def test_paper_set_is_user_scoped_and_rejects_unowned_project(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        first = register(client, "paper-set-a@example.com")
        second = register(client, "paper-set-b@example.com")
        first_headers = auth_header(first)
        second_headers = auth_header(second)
        project = client.post(
            "/api/projects",
            headers=first_headers,
            json={"name": "A only", "description": None, "broad_direction": "TSAD"},
        ).json()
        papers = _fixture_papers(client, first_headers)

        denied_create = client.post(
            "/api/paper-sets",
            headers=second_headers,
            json={
                "project_id": project["id"],
                "purpose": "gap",
                "name": "illegal",
                "paper_ids": [papers[0]["id"]],
            },
        )
        assert denied_create.status_code == 404

        created = client.post(
            "/api/paper-sets",
            headers=first_headers,
            json={
                "project_id": project["id"],
                "purpose": "gap",
                "name": "legal",
                "paper_ids": [papers[0]["id"]],
            },
        )
        paper_set_id = created.json()["id"]
        denied_read = client.get(f"/api/paper-sets/{paper_set_id}", headers=second_headers)
        assert denied_read.status_code == 404


def test_paper_set_requires_at_least_one_paper(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        owner = register(client, "paper-set-empty@example.com")
        response = client.post(
            "/api/paper-sets",
            headers=auth_header(owner),
            json={"purpose": "manual", "name": "empty", "paper_ids": []},
        )
        assert response.status_code == 422
