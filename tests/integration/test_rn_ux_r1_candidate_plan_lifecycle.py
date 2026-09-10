"""Acceptance-only candidate -> human confirmation -> plan lifecycle tests.

These tests deliberately use the existing local cited-material fixture.  The
fixture is synthetic acceptance data and is not a research claim or a domain
fixture; the tests exercise the post-gate state machine only.
"""

from pathlib import Path

from cited_gap_fixture import add_cited_materials
from fastapi.testclient import TestClient
from test_gap_workflow import register, settings_for

from research_navigator.main import create_app
from research_navigator.models import Paper

ACCEPTANCE_FIXTURE = {
    "fixture_type": "synthetic_acceptance_candidate",
    "scientific_claim_allowed": False,
    "domain_fixture_count_contribution": 0,
    "real_research_evidence": False,
}


def _challenged_candidate(app, client: TestClient, headers: dict[str, str]):
    project = client.post(
        "/api/projects",
        headers=headers,
        json={
            "name": "E2.4 acceptance-only candidate",
            "broad_direction": "synthetic state-machine fixture",
        },
    )
    assert project.status_code == 201, project.text
    project_payload = project.json()

    search = client.post(
        "/api/search/papers",
        headers=headers,
        json={"query": "anomaly detection", "sources": ["fixture"], "limit": 2},
    )
    assert search.status_code == 200, search.text
    paper_ids = [paper["id"] for paper in search.json()["papers"]]
    assert len(paper_ids) == 2
    for paper_id in paper_ids:
        analyzed = client.post(
            f"/api/papers/{paper_id}/analyze",
            headers=headers,
            json={"project_id": project_payload["id"]},
        )
        assert analyzed.status_code == 200, analyzed.text

    # This is the existing local acceptance fixture boundary, not a domain
    # evidence assertion and not a production database write.
    add_cited_materials(client.app, project_payload["id"], paper_ids)
    generated = client.post(
        "/api/gaps/generate",
        headers={**headers, "Idempotency-Key": "e2-4-acceptance-generate"},
        json={"project_id": project_payload["id"], "paper_ids": paper_ids},
    )
    assert generated.status_code == 201, generated.text
    candidate = generated.json()
    challenged = client.post(
        f"/api/gaps/{candidate['id']}/challenge",
        headers=headers,
        json={},
    )
    assert challenged.status_code == 200, challenged.text
    challenged_payload = challenged.json()
    assert challenged_payload["status"] == "pending_confirmation"
    assert challenged_payload["challenge_completed_at"] is not None
    return project_payload, paper_ids, challenged_payload


def test_acceptance_candidate_confirmation_and_plan_persistence(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = register(client)
        project, paper_ids, candidate = _challenged_candidate(app, client, headers)
        assert ACCEPTANCE_FIXTURE["fixture_type"] == "synthetic_acceptance_candidate"
        assert ACCEPTANCE_FIXTURE["scientific_claim_allowed"] is False
        assert ACCEPTANCE_FIXTURE["domain_fixture_count_contribution"] == 0
        assert ACCEPTANCE_FIXTURE["real_research_evidence"] is False

        blocked = client.post(
            "/api/plans",
            headers=headers,
            json={"project_id": project["id"], "gap_id": candidate["id"]},
        )
        assert blocked.status_code == 409, blocked.text
        assert candidate["status"] == "pending_confirmation"

        confirm_headers = {**headers, "Idempotency-Key": "e2-4-acceptance-confirm"}
        confirmed = client.post(
            f"/api/gaps/{candidate['id']}/confirm",
            headers=confirm_headers,
            json={"confirmed": True, "note": "仅验证状态机，不代表科学结论"},
        )
        assert confirmed.status_code == 200, confirmed.text
        confirmed_payload = confirmed.json()
        assert confirmed_payload["status"] == "confirmed"
        assert confirmed_payload["confirmed_at"] is not None
        assert confirmed_payload["human_confirmation_note"] == "仅验证状态机，不代表科学结论"

        replay = client.post(
            f"/api/gaps/{candidate['id']}/confirm",
            headers=confirm_headers,
            json={"confirmed": True, "note": "仅验证状态机，不代表科学结论"},
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["id"] == candidate["id"]
        assert replay.json()["status"] == "confirmed"
        assert replay.json()["confirmed_at"] == confirmed_payload["confirmed_at"]

        conflicting_replay = client.post(
            f"/api/gaps/{candidate['id']}/confirm",
            headers=confirm_headers,
            json={"confirmed": True, "note": "不同请求内容"},
        )
        assert conflicting_replay.status_code == 409, conflicting_replay.text

        plan_headers = {**headers, "Idempotency-Key": "e2-4-acceptance-plan"}
        created = client.post(
            "/api/plans",
            headers=plan_headers,
            json={"project_id": project["id"], "gap_id": candidate["id"]},
        )
        assert created.status_code == 201, created.text
        plan = created.json()
        assert plan["gap_id"] == candidate["id"]
        assert plan["project_id"] == project["id"]
        assert plan["review_required"] is False
        assert plan["items"]
        assert all(item["purpose"] for item in plan["items"])
        assert all(item["expected_output"] for item in plan["items"])

        item = plan["items"][0]
        edited = client.put(
            f"/api/plan-items/{item['id']}",
            headers=headers,
            json={
                "status": "skipped",
                "title": "核对测试候选的状态边界",
                "purpose": "验证显式确认前后的服务端门禁",
                "expected_output": "状态机回归记录",
                "notes": "acceptance-only fixture",
            },
        )
        assert edited.status_code == 200, edited.text
        completed = client.put(
            f"/api/plan-items/{item['id']}",
            headers=headers,
            json={"status": "done"},
        )
        assert completed.status_code == 200, completed.text

        duplicate_plan = client.post(
            "/api/plans",
            headers=plan_headers,
            json={"project_id": project["id"], "gap_id": candidate["id"]},
        )
        assert duplicate_plan.status_code == 201, duplicate_plan.text
        assert duplicate_plan.json()["id"] == plan["id"]

    # A fresh client/session can read the persisted state; the fixture remains
    # local SQLite state and never touches a real domain or cloud database.
    with TestClient(app) as reloaded_client:
        reloaded_headers = {**headers}
        stored = reloaded_client.get(f"/api/plans/{plan['id']}", headers=reloaded_headers)
        assert stored.status_code == 200, stored.text
        stored_payload = stored.json()
        stored_item = next(row for row in stored_payload["items"] if row["id"] == item["id"])
        assert stored_item["status"] == "done"
        assert stored_item["purpose"] == "验证显式确认前后的服务端门禁"
        assert stored_item["expected_output"] == "状态机回归记录"
        assert stored_payload["review_required"] is False

        with app.state.database.session() as session:
            paper = session.get(Paper, paper_ids[0])
            assert paper is not None
            paper.abstract = f"{paper.abstract} Material version changed for E2.4."
            session.commit()

        stale_plan = reloaded_client.get(f"/api/plans/{plan['id']}", headers=reloaded_headers)
        assert stale_plan.status_code == 200, stale_plan.text
        assert stale_plan.json()["review_required"] is True
        stale_update = reloaded_client.put(
            f"/api/plan-items/{item['id']}",
            headers=reloaded_headers,
            json={"status": "pending"},
        )
        assert stale_update.status_code == 409, stale_update.text


def test_acceptance_candidate_staleness_blocks_confirmation_and_old_id(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = register(client)
        project, paper_ids, candidate = _challenged_candidate(app, client, headers)

        with app.state.database.session() as session:
            paper = session.get(Paper, paper_ids[0])
            assert paper is not None
            paper.abstract = f"{paper.abstract} Stale material for E2.4."
            session.commit()

        stale_confirm = client.post(
            f"/api/gaps/{candidate['id']}/confirm",
            headers={**headers, "Idempotency-Key": "e2-4-stale-confirm"},
            json={"confirmed": True},
        )
        assert stale_confirm.status_code == 409, stale_confirm.text

        stale_read = client.get(f"/api/gaps/{candidate['id']}", headers=headers)
        assert stale_read.status_code == 200, stale_read.text
        assert stale_read.json()["review_required"] is True
        assert stale_read.json()["status"] == "pending_confirmation"

        stale_plan = client.post(
            "/api/plans",
            headers=headers,
            json={"project_id": project["id"], "gap_id": candidate["id"]},
        )
        assert stale_plan.status_code == 409, stale_plan.text

        old_candidate = client.post(
            "/api/gaps/999999/confirm",
            headers=headers,
            json={"confirmed": True},
        )
        assert old_candidate.status_code == 404, old_candidate.text
