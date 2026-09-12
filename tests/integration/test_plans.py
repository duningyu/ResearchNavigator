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


def test_plan_can_only_be_created_from_confirmed_gap_and_items_are_persisted(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        auth = client.post(
            "/api/auth/register",
            json={
                "email": "plan@example.com",
                "password": "research-pass-123",
                "display_name": "Plan User",
            },
        ).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        project = client.post(
            "/api/projects",
            headers=headers,
            json={"name": "Plan Project", "broad_direction": "时序异常预测"},
        ).json()
        papers = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "anomaly detection", "sources": ["fixture"], "limit": 1},
        ).json()["papers"]
        paper_id = papers[0]["id"]
        client.post(f"/api/papers/{paper_id}/analyze", headers=headers, json={})
        add_cited_materials(client.app, project["id"], [paper_id])
        gap = client.post(
            "/api/gaps/generate",
            headers=headers,
            json={"project_id": project["id"], "paper_ids": [paper_id]},
        ).json()
        blocked = client.post(
            "/api/plans",
            headers=headers,
            json={"project_id": project["id"], "gap_id": gap["id"]},
        )
        assert blocked.status_code == 409

        client.post(f"/api/gaps/{gap['id']}/challenge", headers=headers, json={})
        client.post(f"/api/gaps/{gap['id']}/confirm", headers=headers, json={"confirmed": True})
        created = client.post(
            "/api/plans",
            headers=headers,
            json={"project_id": project["id"], "gap_id": gap["id"]},
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert len(payload["items"]) >= 6
        assert all(item.get("expected_output") for item in payload["items"])
        assert len({item["expected_output"] for item in payload["items"]}) == len(payload["items"])
        assert all(item.get("purpose") for item in payload["items"])
        assert {item["category"] for item in payload["items"]} >= {
            "prerequisite_reading",
            "reproduction",
            "minimal_experiment",
            "risk_check",
        }

        item = payload["items"][0]
        updated = client.put(
            f"/api/plan-items/{item['id']}",
            headers=headers,
            json={"status": "done", "notes": "已完成"},
        )
        assert updated.status_code == 200
        stored = client.get(f"/api/plans/{payload['id']}", headers=headers).json()
        assert any(row["status"] == "done" for row in stored["items"])
        for state in ("skipped", "pending"):
            edited = client.put(
                f"/api/plan-items/{item['id']}",
                headers=headers,
                json={
                    "status": state,
                    "title": "核对两篇原文的任务定义",
                    "description": "产出：一份标注来源与不确定项的对照表",
                    "expected_output": "任务定义对照表，标注待核验条件",
                    "purpose": "确认任务是否可比较",
                },
            )
            assert edited.status_code == 200
            fresh = client.get(f"/api/plans/{payload['id']}", headers=headers).json()
            actual = next(row for row in fresh["items"] if row["id"] == item["id"])
            assert actual["status"] == state
            assert actual["title"] == "核对两篇原文的任务定义"
            assert actual["description"].startswith("产出：")
            assert actual["expected_output"] == "任务定义对照表，标注待核验条件"
            assert actual["purpose"] == "确认任务是否可比较"


def test_reading_plan_can_be_created_without_a_gap(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        auth = client.post(
            "/api/auth/register",
            json={
                "email": "reading@example.com",
                "password": "research-pass-123",
                "display_name": "Reader",
            },
        ).json()
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        project = client.post(
            "/api/projects", headers=headers,
            json={"name": "Reading Project", "broad_direction": "时序异常预测"},
        ).json()
        response = client.post(
            "/api/plans", headers=headers,
            json={
                "project_id": project["id"],
                "gap_id": None,
                "title": "阅读三篇摘要并记录证据边界",
                "objective": "先确认任务定义、适用条件和待核验问题。",
            },
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["gap_id"] is None
        assert payload["review_required"] is False
        assert payload["objective"] == "先确认任务定义、适用条件和待核验问题。"
