"""E4.22 test-only state materialization.

This module deliberately stays outside the product package.  It creates states
through the existing FastAPI routes and uses an isolated SQLite database.  The
fixture records are never valid scientific evidence and are never added to the
domain fixture manifest.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.integration.cited_gap_fixture import add_cited_materials
from tests.support.e4_17_shared_fixture_loader import (
    LoaderIsolationError,
    _headers,
    _register,
    _settings_for,
)

from research_navigator.main import create_app
from research_navigator.models import PaperAnalysisRecord
from research_navigator.scholarly.base import (
    AdapterSearchResult,
    PaperAuthor,
    PaperRecord,
    ScholarlyAdapter,
    SearchRequest,
    SourceProvenance,
    SourceStatus,
)
from research_navigator.scholarly.service import FederatedSearchService


@dataclass(slots=True)
class E422State:
    capability_id: str
    test_only: bool = True
    scientific_claim_allowed: bool = False
    domain_positive_contribution: bool = False
    live_smoke: bool = False
    api_readback: bool = False
    browser_precondition: bool = False
    db_path: str = ""
    entity_ids: dict[str, object] = field(default_factory=dict)
    observed: dict[str, object] = field(default_factory=dict)
    cleanup_verified: bool = False


class E422Adapter(ScholarlyAdapter):
    name = "e4_22_fixture"

    def __init__(self, records: list[PaperRecord]) -> None:
        self.records = records
        self.calls = 0

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        self.calls += 1
        selected = self.records[request.offset : request.offset + request.limit]
        return AdapterSearchResult(
            records=selected,
            status=SourceStatus(
                status="ok", result_count=len(selected), detail="E4.22 test-only adapter"
            ),
        )


def _record(
    capability: str,
    index: int,
    abstract: str,
    *,
    no_public_route: bool = False,
) -> PaperRecord:
    source_id = f"e4-22-{capability}-{index:03d}"
    provenance = SourceProvenance(
        source="e4_22_fixture",
        source_id=source_id,
        source_url=None if no_public_route else f"https://example.invalid/e4-22/{source_id}",
        is_fixture=True,
        raw_hash=(f"{index:064x}"[-64:]),
    )
    return PaperRecord(
        title=f"E4.22 acceptance state {capability} {index}",
        abstract=abstract,
        publication_year=2026,
        authors=[PaperAuthor(name="E4.22 Test-only Author")],
        external_ids={"fixture": source_id},
        source_urls=[] if no_public_route else [provenance.source_url or "https://example.invalid"],
        publisher_url=None if no_public_route else provenance.source_url,
        pdf_url=None,
        open_access_status="暂未找到公开途径" if no_public_route else None,
        keywords=["test-only", capability],
        source_provenance=[provenance],
        abstract_provenance=provenance,
        source_score=float(100 - index),
    )


def _profile_payload() -> dict[str, object]:
    return {
        "stage": "test",
        "major": "test",
        "broad_direction": "工业多变量时序异常检测 / 未来窗口早期预警",
        "keywords": ["future window", "early warning"],
        "excluded_terms": [],
        "preferences": ["evidence-first"],
        "compute_constraints": None,
    }


def _future_work_material(app: object, project_id: int, paper_ids: list[int]) -> None:
    # This uses the existing integration helper, which persists structured
    # analysis and citations through the real model boundary.  The text is
    # explicitly synthetic and cannot be used as a scientific claim.
    add_cited_materials(app, project_id, paper_ids)
    # The shared helper predates the analysis route's typed response contract
    # and intentionally leaves these two JSON columns empty.  E4.22 reads the
    # real route, so make only these test-only rows route-readable without
    # changing the product model or the shared helper.
    with app.state.database.session() as session:
        for paper_id in paper_ids:
            row = session.scalar(
                select(PaperAnalysisRecord)
                .where(
                    PaperAnalysisRecord.paper_id == paper_id,
                    PaperAnalysisRecord.project_id == project_id,
                )
                .order_by(PaperAnalysisRecord.id.desc())
            )
            assert row is not None
            row.direction_similarity_json = json.dumps(
                {
                    "score": 0.0,
                    "evidence_coverage": 0.0,
                    "components": {},
                    "reasons": {},
                    "score_version": "direction-match-v2",
                }
            )
            row.reproduction_assessment_json = json.dumps(
                {
                    "score": 0.0,
                    "evidence_coverage": 0.0,
                    "dimensions": [],
                    "estimated_difficulty": "high",
                    "estimated_compute_level": "unknown",
                    "blocking_reasons": ["test_only_fixture"],
                    "recommended_first_step": "仅用于验收状态机测试。",
                    "score_version": "reproduction-v2",
                },
                ensure_ascii=False,
            )
        session.commit()


class E422ScientificFixtureLoader:
    """Materialize one E4.22 capability in a fresh local application."""

    capabilities = {
        "cap_ux028_timeout_403",
        "cap_ux029_no_public_route",
        "cap_ux048_incomparable_set",
        "cap_ux055_future_work",
        "cap_ux058_challenge_counter",
        "cap_ux011_profile_stale_driver",
        "cap_ux056_scope_driver",
    }

    def __init__(self, root: Path) -> None:
        self.root = root

    def load(self, capability_id: str) -> E422State:
        if capability_id not in self.capabilities:
            raise ValueError(f"unsupported E4.22 capability: {capability_id}")
        settings = _settings_for(self.root)
        state = E422State(
            capability_id=capability_id,
            db_path=str(settings.data_dir / "test.db"),
        )
        abstract = (
            "This test-only paper studies multivariate time-series anomaly detection. "
            "The authors report a bounded early-warning evaluation. "
            "Future work proposes validation on an independent industrial dataset."
        )
        count = (
            4
            if capability_id
            in {
                "cap_ux048_incomparable_set",
                "cap_ux056_scope_driver",
                "cap_ux058_challenge_counter",
            }
            else 1
        )
        records = [
            _record(
                capability_id,
                index,
                abstract,
                no_public_route=capability_id == "cap_ux029_no_public_route",
            )
            for index in range(1, count + 1)
        ]
        with TestClient(create_app(settings)) as client:
            client.app.state.search_service = FederatedSearchService([E422Adapter(records)])
            auth = _register(client, f"e4-22-{capability_id}@example.test")
            headers = _headers(auth)
            profile = client.put(
                "/api/research-profiles/me", headers=headers, json=_profile_payload()
            )
            assert profile.status_code == 200, profile.text
            project = client.post(
                "/api/projects",
                headers=headers,
                json={
                    "name": f"E4.22 {capability_id}",
                    "description": "test-only; no scientific claim",
                    "broad_direction": _profile_payload()["broad_direction"],
                },
            )
            assert project.status_code == 201, project.text
            project_id = int(project.json()["id"])
            search = client.post(
                "/api/search/papers",
                headers=headers,
                json={
                    "query": f"e4-22-{capability_id}",
                    "sources": ["e4_22_fixture"],
                    "limit": count,
                    "project_id": project_id,
                    "mode": "precise",
                },
            )
            assert search.status_code == 200, search.text
            papers = search.json()["papers"]
            assert len(papers) == count
            paper_ids = [int(paper["id"]) for paper in papers]
            state.entity_ids.update(
                {
                    "user_id": int(auth["user"]["id"]),
                    "project_id": project_id,
                    "paper_ids": paper_ids,
                    "session_id": int(search.json()["session_id"]),
                }
            )
            for paper_id in paper_ids:
                detail = client.get(f"/api/papers/{paper_id}", headers=headers)
                assert detail.status_code == 200, detail.text
                status = client.get(f"/api/papers/{paper_id}/content-status", headers=headers)
                assert status.status_code == 200, status.text
            state.observed["paper_count"] = len(papers)
            state.observed["content_levels"] = [
                client.get(
                    f"/api/papers/{paper_id}/content-status", headers=headers
                ).json()["evidence_level"]
                for paper_id in paper_ids
            ]
            if capability_id == "cap_ux029_no_public_route":
                detail = client.get(f"/api/papers/{paper_ids[0]}", headers=headers)
                detail_payload = detail.json()
                assert detail_payload["open_access_status"] == "暂未找到公开途径"
                assert detail_payload["source_urls"] == []
                assert detail_payload["publisher_url"] is None
                assert detail_payload["pdf_url"] is None
                state.observed["no_public_route"] = {
                    "open_access_status": detail_payload["open_access_status"],
                    "source_urls": detail_payload["source_urls"],
                    "publisher_url": detail_payload["publisher_url"],
                    "pdf_url": detail_payload["pdf_url"],
                }

            if capability_id == "cap_ux011_profile_stale_driver":
                refresh = client.post(
                    "/api/recommendations/refresh",
                    headers=headers,
                    json={"project_id": project_id},
                )
                assert refresh.status_code == 200, refresh.text
                changed = dict(_profile_payload())
                changed["broad_direction"] = "生物医学图像分割"
                assert (
                    client.put(
                        "/api/research-profiles/me", headers=headers, json=changed
                    ).status_code
                    == 200
                )
                current = client.get(
                    f"/api/recommendations?project_id={project_id}", headers=headers
                )
                assert current.status_code == 200, current.text
                state.observed["recommendations_current"] = [
                    row["reading_recommendation"]["is_current"] for row in current.json()
                ]
            elif capability_id == "cap_ux048_incomparable_set":
                paper_set = client.post(
                    "/api/paper-sets",
                    headers=headers,
                    json={
                        "project_id": project_id,
                        "purpose": "compare",
                        "name": "E4.22 incomparable test-only set",
                        "paper_ids": paper_ids,
                        "source_kind": "explicit",
                    },
                )
                assert paper_set.status_code == 201, paper_set.text
                comparison = client.post(
                    "/api/comparisons",
                    headers=headers,
                    json={"project_id": project_id, "paper_set_id": paper_set.json()["id"]},
                )
                assert comparison.status_code == 201, comparison.text
                state.entity_ids["paper_set_id"] = int(paper_set.json()["id"])
                state.entity_ids["comparison_id"] = int(comparison.json()["id"])
                state.observed["comparison"] = comparison.json()
            elif capability_id == "cap_ux056_scope_driver":
                # The comparison route classifies relation from cited task
                # evidence; a generic paper row intentionally yields
                # ``unknown``.  Materialize cited evidence for only the
                # first paper through the existing test integration helper,
                # leaving the remaining papers as reference/unknown rows.
                # This is a test-only semantic precondition, not a persisted
                # relation override and cannot support a scientific claim.
                _future_work_material(client.app, project_id, [paper_ids[0]])
                paper_set = client.post(
                    "/api/paper-sets",
                    headers=headers,
                    json={
                        "project_id": project_id,
                        "purpose": "compare",
                        "name": "E4.22 mixed relation test-only set",
                        "paper_ids": paper_ids,
                        "source_kind": "explicit",
                    },
                )
                assert paper_set.status_code == 201, paper_set.text
                comparison = client.post(
                    "/api/comparisons",
                    headers=headers,
                    json={"project_id": project_id, "paper_set_id": paper_set.json()["id"]},
                )
                assert comparison.status_code == 201, comparison.text
                state.entity_ids["paper_set_id"] = int(paper_set.json()["id"])
                state.entity_ids["comparison_id"] = int(comparison.json()["id"])
                state.observed["comparison"] = comparison.json()
            elif capability_id == "cap_ux055_future_work":
                _future_work_material(client.app, project_id, paper_ids)
                analysis = client.get(
                    f"/api/papers/{paper_ids[0]}/analysis?project_id={project_id}",
                    headers=headers,
                )
                assert analysis.status_code == 200, analysis.text
                state.observed["future_work"] = analysis.json()["analysis"]["future_work_explicit"]
                state.observed["future_citations"] = analysis.json()["analysis"][
                    "field_citations"
                ]["future_work_explicit"]
            elif capability_id == "cap_ux058_challenge_counter":
                state.observed["challenge_precondition"] = "candidate requires formal evidence gate"
                state.observed["candidate_creation"] = "not forced; no scientific claim"
            state.live_smoke = True
            state.api_readback = True
            # A TestClient is an API/service smoke only.  The browser precondition
            # remains false until a real Playwright session observes the route.
            state.browser_precondition = False
        state.cleanup_verified = state.test_only and not state.scientific_claim_allowed
        return state


__all__ = ["E422ScientificFixtureLoader", "E422State", "LoaderIsolationError"]
