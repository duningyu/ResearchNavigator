from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from research_navigator.config import Settings
from research_navigator.main import create_app


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


def register(client: TestClient, email: str, name: str) -> tuple[dict[str, str], int]:
    body = client.post(
        "/api/auth/register",
        json={"email": email, "password": "research-pass-123", "display_name": name},
    ).json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


def create_and_freeze_study(client: TestClient, owner: dict[str, str]) -> dict[str, object]:
    created = client.post(
        "/api/evaluations/studies",
        headers=owner,
        json={
            "name": "Evidence explanation comparison",
            "description": "Blind comparison of deterministic and evidence-enriched outputs.",
            "study_version": "expert-study-v1",
            "randomized_seed": "frozen-seed-2026",
            "protocol": {
                "minimum_real_experts": 2,
                "score_scale": [1, 5],
                "dimensions": [
                    "evidence_correctness",
                    "evidence_sufficiency",
                    "citation_usefulness",
                    "missing_field_correctness",
                ],
            },
            "tasks": [
                {
                    "task_key": "paper-1-analysis",
                    "baseline_payload": {"summary": "Baseline summary", "citations": ["c1"]},
                    "candidate_payload": {"summary": "Candidate summary", "citations": ["c1"]},
                    "position": 1,
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["status"] == "draft"
    assert draft["expert_outcome_validation"] == "awaiting_real_experts"

    blocked = client.post(
        f"/api/evaluations/studies/{draft['id']}/assignments",
        headers=owner,
        json={"expert_user_id": 999, "is_simulated": False},
    )
    assert blocked.status_code == 409

    frozen = client.post(f"/api/evaluations/studies/{draft['id']}/freeze", headers=owner)
    assert frozen.status_code == 200, frozen.text
    result = frozen.json()
    assert result["status"] == "frozen"
    assert len(result["frozen_input_hash"]) == 64
    return result


def submit_rating(
    client: TestClient,
    headers: dict[str, str],
    assignment_id: int,
    *,
    preference: str = "A",
) -> dict[str, object]:
    started = client.post(f"/api/evaluations/assignments/{assignment_id}/start", headers=headers)
    assert started.status_code == 200, started.text
    rated = client.post(
        f"/api/evaluations/assignments/{assignment_id}/ratings",
        headers=headers,
        json={
            "evidence_correctness": 4,
            "evidence_sufficiency": 4,
            "citation_usefulness": 5,
            "missing_field_correctness": 4,
            "preference": preference,
            "comments": "The cited claims are easier to audit.",
        },
    )
    assert rated.status_code == 201, rated.text
    return rated.json()


def test_simulated_ratings_never_unlock_expert_validation(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        owner, _ = register(client, "study-owner@example.com", "Owner")
        simulated, simulated_id = register(client, "simulated@example.com", "Simulated")
        study = create_and_freeze_study(client, owner)

        assigned = client.post(
            f"/api/evaluations/studies/{study['id']}/assignments",
            headers=owner,
            json={"expert_user_id": simulated_id, "is_simulated": True},
        )
        assert assigned.status_code == 201, assigned.text
        assignment = assigned.json()[0]
        assert assignment["is_simulated"] is True
        assert {variant["label"] for variant in assignment["variants"]} == {"A", "B"}
        assert all("source" not in variant for variant in assignment["variants"])

        submit_rating(client, simulated, assignment["id"])
        results = client.get(f"/api/evaluations/studies/{study['id']}/results", headers=owner)
        assert results.status_code == 200, results.text
        payload = results.json()
        assert payload["simulated_count"] == 1
        assert payload["real_expert_count"] == 0
        assert payload["validation_status"] == "awaiting_real_experts"
        assert payload["claim_boundary"] == (
            "Simulated or developer ratings are workflow evidence only and are not "
            "real expert validation."
        )


def test_two_real_experts_produce_blinded_aggregate_without_cross_user_access(
    tmp_path: Path,
) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        owner, _ = register(client, "owner2@example.com", "Owner")
        expert_a, expert_a_id = register(client, "expert-a@example.com", "Expert A")
        expert_b, expert_b_id = register(client, "expert-b@example.com", "Expert B")
        outsider, _ = register(client, "outsider@example.com", "Outsider")
        study = create_and_freeze_study(client, owner)

        assignments: list[tuple[dict[str, str], dict[str, object]]] = []
        for headers, expert_id in ((expert_a, expert_a_id), (expert_b, expert_b_id)):
            response = client.post(
                f"/api/evaluations/studies/{study['id']}/assignments",
                headers=owner,
                json={"expert_user_id": expert_id, "is_simulated": False},
            )
            assert response.status_code == 201, response.text
            assignments.append((headers, response.json()[0]))

        own_queue = client.get("/api/evaluations/assignments", headers=expert_a)
        assert own_queue.status_code == 200
        assert [item["id"] for item in own_queue.json()] == [assignments[0][1]["id"]]
        assert (
            client.get(
                f"/api/evaluations/studies/{study['id']}/results", headers=outsider
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/evaluations/assignments/{assignments[0][1]['id']}/start",
                headers=expert_b,
            ).status_code
            == 404
        )

        for headers, assignment in assignments:
            submit_rating(client, headers, int(assignment["id"]), preference="A")

        results = client.get(
            f"/api/evaluations/studies/{study['id']}/results", headers=owner
        ).json()
        assert results["real_expert_count"] == 2
        assert results["simulated_count"] == 0
        assert results["validation_status"] == "real_expert_results_available"
        assert results["metrics"]["rating_count"] == 2
        assert results["metrics"]["preference_agreement"] == 1.0
        assert results["metrics"]["mean_scores"]["citation_usefulness"] == 5.0
        assert results["claim_boundary"].startswith(
            "Results are available from self-declared non-simulated reviewers"
        )


def test_study_owner_can_list_and_reopen_frozen_protocol(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        owner, _ = register(client, "study-list-owner@example.com", "Owner")
        outsider, _ = register(client, "study-list-outsider@example.com", "Outsider")
        study = create_and_freeze_study(client, owner)

        listed = client.get("/api/evaluations/studies", headers=owner)
        assert listed.status_code == 200, listed.text
        assert [item["id"] for item in listed.json()] == [study["id"]]
        reopened = client.get(f"/api/evaluations/studies/{study['id']}", headers=owner)
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["frozen_input_hash"] == study["frozen_input_hash"]
        assert (
            client.get(f"/api/evaluations/studies/{study['id']}", headers=outsider).status_code
            == 404
        )
