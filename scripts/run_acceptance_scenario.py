#!/usr/bin/env python3
"""HTTP-first deterministic acceptance scenario for ResearchNavigator.

After application bootstrap every scenario mutation is executed through public HTTP APIs.
The optional ``--confirm-demo-gap`` flag is deliberately labelled simulated human confirmation.
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any, Protocol

from fastapi.testclient import TestClient

from research_navigator.config import Settings
from research_navigator.main import create_app


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: Any): ...
    def post(self, url: str, **kwargs: Any): ...
    def put(self, url: str, **kwargs: Any): ...


def _ok(response, expected: set[int] | None = None):
    allowed = expected if expected is not None else {200, 201, 202, 204}
    if response.status_code not in allowed:
        raise RuntimeError(
            f"HTTP {response.status_code} for {response.request.method} "
            f"{response.request.url}: {response.text}"
        )
    return None if response.status_code == 204 else response.json()


def _idem(version: str, operation: str) -> dict[str, str]:
    return {"Idempotency-Key": f"acceptance:{version}:{operation}", "X-Scenario-Version": version}


def run_scenario(
    client: HttpClient, *, scenario_version: str, confirm_demo_gap: bool = False
) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:10]
    email = f"acceptance-{suffix}@example.invalid"
    password = "acceptance-research-pass-123"
    auth = _ok(
        client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "display_name": "Acceptance Researcher"},
        )
    )
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    _ok(
        client.put(
            "/api/research-profiles/me",
            headers=headers,
            json={
                "stage": "硕士研究",
                "major": "时序异常检测",
                "broad_direction": "未来窗口异常风险排序与证据约束研究",
                "keywords": ["future horizon", "anomaly ranking", "evidence-aware"],
                "excluded_terms": [],
                "preferences": ["证据优先", "可复现"],
                "compute_constraints": "single GPU",
            },
        )
    )
    project = _ok(
        client.post(
            "/api/projects",
            headers={**headers, **_idem(scenario_version, "project")},
            json={
                "name": "HTTP-first acceptance project",
                "description": "Deterministic acceptance fixture project",
                "broad_direction": "未来窗口异常风险排序",
            },
        )
    )
    search = _ok(
        client.post(
            "/api/search/papers",
            headers=headers,
            json={
                "query": "time series anomaly detection",
                "mode": "discovery",
                "sources": ["fixture"],
                "limit": 50,
                "project_id": project["id"],
            },
        )
    )
    if len(search["papers"]) < 2:
        raise RuntimeError("Fixture acceptance corpus must contain at least two papers")
    selected_ids = [paper["id"] for paper in search["papers"][:2]]
    for index, paper_id in enumerate(selected_ids):
        _ok(
            client.post(
                f"/api/papers/{paper_id}/analyze",
                headers=headers,
                json={"project_id": project["id"]},
            )
        )
        if index == 0:
            _ok(
                client.post(
                    "/api/library/favorites",
                    headers={**headers, **_idem(scenario_version, "favorite")},
                    json={"paper_id": paper_id},
                )
            )
            _ok(
                client.post(
                    "/api/library/notes",
                    headers={**headers, **_idem(scenario_version, "note")},
                    json={
                        "paper_id": paper_id,
                        "content": "Acceptance note created through HTTP API.",
                    },
                )
            )
    paper_set = _ok(
        client.post(
            "/api/paper-sets",
            headers={**headers, **_idem(scenario_version, "paper-set")},
            json={
                "project_id": project["id"],
                "purpose": "compare",
                "name": "Acceptance explicit paper set",
                "paper_ids": selected_ids,
                "source_kind": "search_session",
            },
        )
    )
    comparison = _ok(
        client.post(
            "/api/comparisons",
            headers=headers,
            json={"project_id": project["id"], "paper_set_id": paper_set["id"]},
        )
    )
    gap_set = _ok(
        client.post(
            "/api/paper-sets",
            headers={**headers, **_idem(scenario_version, "gap-paper-set")},
            json={
                "project_id": project["id"],
                "purpose": "gap",
                "name": "Acceptance gap evidence set",
                "paper_ids": selected_ids,
                "source_kind": "search_session",
            },
        )
    )
    gap = _ok(
        client.post(
            "/api/gaps/generate",
            headers={**headers, **_idem(scenario_version, "gap")},
            json={"project_id": project["id"], "paper_set_id": gap_set["id"]},
        )
    )
    gap = _ok(
        client.post(
            f"/api/gaps/{gap['id']}/challenge",
            headers=headers,
            json={"additional_terms": ["counter evidence", "adjacent method"]},
        )
    )

    plan = None
    human_confirmation = "not_performed"
    if confirm_demo_gap:
        gap = _ok(
            client.post(
                f"/api/gaps/{gap['id']}/confirm",
                headers=headers,
                json={
                    "confirmed": True,
                    "note": (
                        "simulated_human_confirmation: automated acceptance flag; "
                        "not an expert review"
                    ),
                },
            )
        )
        human_confirmation = "simulated_human_confirmation"
        plan = _ok(
            client.post(
                "/api/plans",
                headers={**headers, **_idem(scenario_version, "plan")},
                json={"project_id": project["id"], "gap_id": gap["id"]},
            )
        )

    return {
        "scenario_version": scenario_version,
        "execution_mode": "http_api_only_after_bootstrap",
        "user_id": auth["user"]["id"],
        "project_id": project["id"],
        "search": {
            "session_id": search["session_id"],
            "mode": search["search_mode"],
            "requested_limit": 50,
            "actual_count": search["result_count"],
            "diversity_seed": search.get("diversity_seed"),
            "composition": search.get("composition", {}),
        },
        "paper_set": {"id": paper_set["id"], "paper_ids": paper_set["paper_ids"]},
        "comparison": {
            "id": comparison["id"],
            "row_count": len(comparison["rows"]),
            "evidence_hash": comparison["evidence_hash"],
        },
        "gap": {
            "id": gap["id"],
            "status": gap["status"],
            "workflow_stage": gap["workflow_stage"],
            "paper_set_id": gap.get("paper_set_id"),
            "explanation_version": (gap.get("explanation") or {}).get("version"),
            "not_novelty_proof": gap["not_novelty_proof"],
        },
        "human_confirmation": human_confirmation,
        "plan": None if plan is None else {"id": plan["id"], "status": plan["status"]},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-version", default="feedback-closure-v1")
    parser.add_argument("--confirm-demo-gap", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    settings = Settings.from_env()
    app = create_app(settings)
    with TestClient(app) as client:
        report = run_scenario(
            client, scenario_version=args.scenario_version, confirm_demo_gap=args.confirm_demo_gap
        )
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
