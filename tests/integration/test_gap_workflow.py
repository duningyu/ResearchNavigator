from pathlib import Path

from cited_gap_fixture import add_cited_materials
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


def register(client: TestClient) -> dict[str, str]:
    auth = client.post(
        "/api/auth/register",
        json={
            "email": "gap@example.com",
            "password": "research-pass-123",
            "display_name": "Gap User",
        },
    ).json()
    return {"Authorization": f"Bearer {auth['access_token']}"}


def test_gap_requires_challenge_before_human_confirmation(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        headers = register(client)
        client.put(
            "/api/research-profiles/me",
            headers=headers,
            json={
                "stage": "硕士一年级",
                "major": "大数据技术与工程",
                "broad_direction": "未来窗口异常风险排序",
                "keywords": ["future horizon", "alert ranking", "fixed alert budget"],
                "excluded_terms": [],
                "preferences": ["复现优先"],
                "compute_constraints": "单卡 GPU",
            },
        )
        project = client.post(
            "/api/projects",
            headers=headers,
            json={
                "name": "TSAD direction",
                "description": "Evidence-bounded topic selection",
                "broad_direction": "未来窗口异常风险排序",
            },
        ).json()
        papers = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "anomaly detection", "sources": ["fixture"], "limit": 2},
        ).json()["papers"]
        paper_ids = [paper["id"] for paper in papers]
        for paper_id in paper_ids:
            analyzed = client.post(
                f"/api/papers/{paper_id}/analyze",
                headers=headers,
                json={"project_id": project["id"]},
            )
            assert analyzed.status_code == 200

        add_cited_materials(client.app, project["id"], paper_ids)

        generated = client.post(
            "/api/gaps/generate",
            headers=headers,
            json={"project_id": project["id"], "paper_ids": paper_ids},
        )
        assert generated.status_code == 201, generated.text
        gap = generated.json()
        assert gap["not_novelty_proof"] is True
        assert gap["status"] == "generated"
        assert gap["evidence_matrix"]

        premature = client.post(
            f"/api/gaps/{gap['id']}/confirm", headers=headers, json={"confirmed": True}
        )
        assert premature.status_code == 409

        challenged = client.post(f"/api/gaps/{gap['id']}/challenge", headers=headers, json={})
        assert challenged.status_code == 200, challenged.text
        challenged_payload = challenged.json()
        assert challenged_payload["status"] == "pending_confirmation"
        assert challenged_payload["challenge_queries"]
        assert challenged_payload["challenge_completed_at"] is not None

        confirmed = client.post(
            f"/api/gaps/{gap['id']}/confirm",
            headers=headers,
            json={"confirmed": True, "note": "导师仍需复核"},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "confirmed"
        assert confirmed.json()["human_confirmation_note"] == "导师仍需复核"


def test_gap_generation_uses_explicit_paper_set_not_latest_search(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        headers = register(client)
        project = client.post(
            "/api/projects",
            headers=headers,
            json={"name": "Explicit set", "broad_direction": "future risk ranking"},
        ).json()
        first_search = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "anomaly detection", "sources": ["fixture"], "limit": 2},
        ).json()
        selected_ids = [paper["id"] for paper in first_search["papers"]]
        add_cited_materials(client.app, project["id"], selected_ids)
        paper_set = client.post(
            "/api/paper-sets",
            headers=headers,
            json={
                "project_id": project["id"],
                "purpose": "gap",
                "name": "Chosen corpus",
                "paper_ids": selected_ids,
                "source_kind": "search_session",
            },
        ).json()
        # A later search must not replace the explicit selection.
        client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "attention", "sources": ["fixture"], "limit": 1},
        )

        generated = client.post(
            "/api/gaps/generate",
            headers=headers,
            json={"project_id": project["id"], "paper_set_id": paper_set["id"]},
        )
        assert generated.status_code == 201, generated.text
        payload = generated.json()
        assert payload["paper_set_id"] == paper_set["id"]
        assert [row["paper_id"] for row in payload["evidence_matrix"]] == selected_ids
        assert payload["direction_snapshot"]["project"]["id"] == project["id"]
        assert payload["explanation"]["not_novelty_proof"] is True
        assert payload["explanation"]["direct_evidence"]
        assert payload["explanation"]["inferences"]
        assert payload["workflow_stage"] == "challenge_required"


def test_gap_explanation_is_versioned_and_plan_blocked_until_human_confirmation(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        headers = register(client)
        project = client.post(
            "/api/projects",
            headers=headers,
            json={"name": "Explain gap", "broad_direction": "未来窗口异常风险排序"},
        ).json()
        papers = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "anomaly detection", "sources": ["fixture"], "limit": 2},
        ).json()["papers"]
        add_cited_materials(client.app, project["id"], [paper["id"] for paper in papers])
        paper_set = client.post(
            "/api/paper-sets",
            headers=headers,
            json={
                "project_id": project["id"],
                "purpose": "gap",
                "name": "Explain set",
                "paper_ids": [paper["id"] for paper in papers],
                "source_kind": "explicit",
            },
        ).json()
        generated = client.post(
            "/api/gaps/generate",
            headers=headers,
            json={"project_id": project["id"], "paper_set_id": paper_set["id"]},
        ).json()

        blocked_plan = client.post(
            "/api/plans",
            headers=headers,
            json={"project_id": project["id"], "gap_id": generated["id"]},
        )
        assert blocked_plan.status_code == 409

        challenged = client.post(
            f"/api/gaps/{generated['id']}/challenge",
            headers=headers,
            json={"additional_terms": ["cross device generalization"]},
        )
        assert challenged.status_code == 200, challenged.text
        payload = challenged.json()
        assert payload["workflow_stage"] == "awaiting_human_confirmation"
        assert payload["explanation"]["version"] >= 2
        assert payload["explanation"]["evidence_hash"]
        assert payload["explanation"]["absent_evidence"]
        assert payload["explanation"]["direction_relation"]
        assert payload["explanation"]["novelty_risk_factors"]
        assert payload["explanation"]["challenge_queries"]
        assert payload["explanation"]["minimum_validation"]
        assert payload["explanation"]["confidence_rationale"]
        assert payload["explanation"]["not_novelty_proof"] is True

        still_blocked = client.post(
            "/api/plans",
            headers=headers,
            json={"project_id": project["id"], "gap_id": generated["id"]},
        )
        assert still_blocked.status_code == 409

        confirmed = client.post(
            f"/api/gaps/{generated['id']}/confirm",
            headers=headers,
            json={"confirmed": True, "note": "界面人工确认；仍非创新性证明"},
        )
        assert confirmed.status_code == 200
        created_plan = client.post(
            "/api/plans",
            headers=headers,
            json={"project_id": project["id"], "gap_id": generated["id"]},
        )
        assert created_plan.status_code == 201, created_plan.text
