"""Create a deterministic fixture-only public demo workspace."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


def _configure_environment(data_dir: Path) -> None:
    database_path = data_dir / "research_navigator.db"
    values = {
        "RN_DATA_DIR": str(data_dir),
        "RN_DATABASE_URL": f"sqlite+pysqlite:///{database_path.as_posix()}",
        "RN_ENVIRONMENT": "demo",
        "RN_PUBLIC_DEMO_MODE": "1",
        "RN_ENABLE_FIXTURE_SOURCE": "1",
        "RN_ENABLE_OPENALEX": "0",
        "RN_ENABLE_CROSSREF": "0",
        "RN_ENABLE_ARXIV": "0",
        "RN_ENABLE_SEMANTIC_SCHOLAR": "0",
        "RN_ANALYSIS_PROVIDER": "deterministic",
    }
    os.environ.update(values)


def _require(response: Any, expected: int, operation: str) -> dict[str, Any]:
    if response.status_code != expected:
        raise RuntimeError(f"{operation} failed ({response.status_code}): {response.text}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{operation} returned a non-object response")
    return payload


def seed(data_dir: Path, *, email: str, password: str) -> dict[str, Any]:
    _configure_environment(data_dir)
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select

    from research_navigator.config import Settings
    from research_navigator.main import create_app
    from research_navigator.models import (
        ComparisonRun,
        Favorite,
        Paper,
        PaperAnalysisRecord,
        PaperSet,
        PaperSource,
        ResearchProject,
        User,
    )

    app = create_app(Settings.from_env())
    with TestClient(app) as client:
        with app.state.database.session() as session:
            existing_users = session.scalar(select(func.count(User.id))) or 0
        if existing_users:
            raise RuntimeError("Public demo seed requires an empty users table")

        auth = _require(
            client.post(
                "/api/auth/register",
                json={"email": email, "password": password, "display_name": "Public Demo"},
            ),
            201,
            "register demo user",
        )
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        _require(
            client.put(
                "/api/research-profiles/me",
                headers=headers,
                json={
                    "stage": "作品集演示（fixture）",
                    "major": "工业时序异常检测",
                    "broad_direction": "未来窗口风险排序与证据审计",
                    "keywords": ["time series", "anomaly detection", "alert ranking"],
                    "excluded_terms": [],
                    "preferences": ["fixture-only", "evidence-first"],
                    "compute_constraints": "演示数据；不代表真实用户研究配置",
                },
            ),
            200,
            "create demo profile",
        )
        project = _require(
            client.post(
                "/api/projects",
                headers={**headers, "Idempotency-Key": "public-demo-project-v1"},
                json={
                    "name": "工业时序异常检测（演示）",
                    "description": "仅包含内置 fixture/synthetic 元数据，不是真实用户项目。",
                    "broad_direction": "未来窗口风险排序",
                },
            ),
            201,
            "create demo project",
        )
        search = _require(
            client.post(
                "/api/search/papers",
                headers=headers,
                json={
                    "query": "time series anomaly detection",
                    "sources": ["fixture"],
                    "limit": 5,
                    "project_id": project["id"],
                },
            ),
            200,
            "search fixture papers",
        )
        papers = search.get("papers")
        if not isinstance(papers, list) or len(papers) < 3:
            raise RuntimeError("Fixture search did not return at least three papers")
        paper_ids = [int(item["id"]) for item in papers[:3]]
        for paper_id in paper_ids:
            _require(
                client.post(
                    f"/api/papers/{paper_id}/analyze",
                    headers=headers,
                    json={"project_id": project["id"], "provider": "deterministic"},
                ),
                200,
                f"analyze fixture paper {paper_id}",
            )
        for index, paper_id in enumerate(paper_ids[:2]):
            _require(
                client.post(
                    "/api/library/favorites",
                    headers={**headers, "Idempotency-Key": f"public-demo-favorite-{index}"},
                    json={"paper_id": paper_id},
                ),
                201,
                f"favorite fixture paper {paper_id}",
            )
        paper_set = _require(
            client.post(
                "/api/paper-sets",
                headers={**headers, "Idempotency-Key": "public-demo-paper-set-v1"},
                json={
                    "project_id": project["id"],
                    "purpose": "compare",
                    "name": "Fixture comparison set",
                    "paper_ids": paper_ids,
                    "source_kind": "explicit",
                },
            ),
            201,
            "create demo paper set",
        )
        _require(
            client.post(
                "/api/comparisons",
                headers=headers,
                json={"project_id": project["id"], "paper_set_id": paper_set["id"]},
            ),
            201,
            "create demo comparison",
        )

        with app.state.database.session() as session:
            counts = {
                "users": session.scalar(select(func.count(User.id))) or 0,
                "projects": session.scalar(select(func.count(ResearchProject.id))) or 0,
                "papers": session.scalar(select(func.count(Paper.id))) or 0,
                "favorites": session.scalar(select(func.count(Favorite.id))) or 0,
                "paper_sets": session.scalar(select(func.count(PaperSet.id))) or 0,
                "comparisons": session.scalar(select(func.count(ComparisonRun.id))) or 0,
                "analyses": session.scalar(select(func.count(PaperAnalysisRecord.id))) or 0,
            }
            non_fixture_sources = session.scalar(
                select(func.count(PaperSource.id)).where(PaperSource.is_fixture.is_(False))
            ) or 0

    database_path = data_dir / "research_navigator.db"
    with sqlite3.connect(database_path) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    receipt: dict[str, Any] = {
        "seed_version": "RN223_PUBLIC_DEMO_SEED_V1",
        **counts,
        "fixture_only": non_fixture_sources == 0,
        "real_world_validation_claimed": False,
        "integrity_check": integrity,
        "demo_email": email,
    }
    (data_dir / "seed_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--email", default="demo@researchnavigator.local")
    parser.add_argument("--password", default="research-demo-223")
    args = parser.parse_args()
    receipt = seed(args.data_dir.resolve(), email=args.email, password=args.password)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
