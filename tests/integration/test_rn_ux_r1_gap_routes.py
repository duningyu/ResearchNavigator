"""Offline persisted HTTP regressions, including pre-R1 legacy records."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_gap_workflow import register, settings_for

from research_navigator.main import create_app
from research_navigator.models import GapCandidate, PaperSet, ResearchPlan, User


def seed_cited_selection(app, user_id, project_id):
    """Real local rows, explicitly synthetic abstract evidence; not a provider stub result."""
    from research_navigator.analysis.structured import CitationLocator, PaperAnalysisOutput
    from research_navigator.models import Paper, PaperAnalysisRecord

    ids = []
    with app.state.database.session() as session:
        for index in range(2):
            problem = "We study semantic segmentation of images."
            limitation = f"Our limitation is evaluation on only synthetic dataset {index}."
            paper = Paper(
                title=f"Synthetic segmentation study {index}",
                normalized_title=f"synthetic segmentation study {index}",
                abstract=problem + " " + limitation,
            )
            session.add(paper)
            session.flush()
            output = PaperAnalysisOutput(
                paper_id=paper.id,
                evidence_level="abstract_only",
                executive_summary=problem,
                summary=problem,
                research_problem=problem,
                limitations_author_stated=[limitation],
                field_states={
                    "research_problem": "evidenced",
                    "limitations_author_stated": "evidenced",
                },
                field_citations={
                    field: [
                        CitationLocator(
                            source_type="abstract", section="Abstract", supporting_text=text
                        )
                    ]
                    for field, text in [
                        ("research_problem", problem),
                        ("limitations_author_stated", limitation),
                    ]
                },
            )
            session.add(
                PaperAnalysisRecord(
                    user_id=user_id,
                    project_id=project_id,
                    paper_id=paper.id,
                    evidence_level="abstract_only",
                    analysis_version="structured-v3",
                    analysis_json=output.model_dump_json(),
                    direction_similarity_json="{}",
                    reproduction_assessment_json="{}",
                )
            )
            ids.append(paper.id)
        session.commit()
    return ids


def generate_valid(app, client, headers):
    project = client.post(
        "/api/projects", headers=headers, json={"name": "semantic segmentation"}
    ).json()
    with app.state.database.session() as session:
        user_id = session.scalar(select(User.id))
    ids = seed_cited_selection(app, user_id, project["id"])
    payload = {"project_id": project["id"], "paper_ids": ids}
    response = client.post(
        "/api/gaps/generate", headers={**headers, "Idempotency-Key": "cited"}, json=payload
    )
    assert response.status_code == 201, response.text
    return response.json(), payload


def test_material_change_invalidates_old_idempotency_replay(tmp_path):
    from research_navigator.models import Paper

    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = register(client)
        gap, payload = generate_valid(app, client, headers)
        assert gap["coverage"]["eligibility"]["allowed"] is True
        with app.state.database.session() as session:
            paper = session.get(Paper, payload["paper_ids"][0])
            paper.abstract = "Corrected material; earlier quotation has been withdrawn."
            session.commit()
        replay = client.post(
            "/api/gaps/generate", headers={**headers, "Idempotency-Key": "cited"}, json=payload
        )
        assert replay.status_code == 409, replay.text


def test_analysis_in_another_project_cannot_authorize_gap(tmp_path):
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = register(client)
        _, payload = generate_valid(app, client, headers)
        other = client.post(
            "/api/projects",
            headers=headers,
            json={"name": "Other project", "broad_direction": "semantic segmentation"},
        ).json()
        response = client.post(
            "/api/gaps/generate",
            headers=headers,
            json={**payload, "project_id": other["id"]},
        )
        assert response.status_code == 409, response.text


@pytest.mark.parametrize(
    "mutation", ["fabricated_quote", "duplicate_work", "arxiv_versions", "negated_task"]
)
def test_structured_labels_do_not_override_actual_material(tmp_path, mutation):
    from research_navigator.models import Paper

    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = register(client)
        project = client.post(
            "/api/projects", headers=headers, json={"name": "semantic segmentation"}
        ).json()
        with app.state.database.session() as session:
            user_id = session.scalar(select(User.id))
        ids = seed_cited_selection(app, user_id, project["id"])
        with app.state.database.session() as session:
            for paper_id in ids:
                paper = session.get(Paper, paper_id)
                if mutation == "fabricated_quote":
                    paper.abstract = "We present unrelated protein folding research."
                elif mutation == "duplicate_work":
                    paper.title = "SAME underlying work"
                    paper.normalized_title = "same underlying work"
                elif mutation == "arxiv_versions":
                    paper.arxiv_id = f"2601.12345v{ids.index(paper_id) + 1}"
                else:
                    # Keep a verbatim citation but the cited task explicitly disclaims relevance.
                    import json

                    from research_navigator.models import PaperAnalysisRecord

                    row = session.scalar(
                        select(PaperAnalysisRecord).where(PaperAnalysisRecord.paper_id == paper_id)
                    )
                    value = json.loads(row.analysis_json)
                    text = "We do not study semantic segmentation of images."
                    paper.abstract = paper.abstract.replace(value["research_problem"], text)
                    value["research_problem"] = text
                    value["field_citations"]["research_problem"][0]["supporting_text"] = text
                    row.analysis_json = json.dumps(value)
            session.commit()
        result = client.post(
            "/api/gaps/generate",
            headers=headers,
            json={"project_id": project["id"], "paper_ids": ids},
        )
        assert result.status_code == 409, result.text


def test_old_gap_read_is_explicitly_review_only(tmp_path):
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = register(client)
        gap, _ = generate_valid(app, client, headers)
        with app.state.database.session() as session:
            row = session.get(GapCandidate, gap["id"])
            row.coverage_json = "{}"
            session.commit()
        read = client.get(f"/api/gaps/{gap['id']}", headers=headers)
        assert read.json()["review_required"] is True
        assert "旧记录" in read.json()["review_reason"]


@pytest.mark.parametrize("source_status", ["ok", "error", "rate_limited", "disabled"])
def test_challenge_quantity_never_increases_confidence_and_errors_cannot_confirm(
    tmp_path, source_status
):
    from unittest.mock import AsyncMock

    from research_navigator.scholarly.base import PaperRecord, SourceStatus
    from research_navigator.scholarly.service import FederatedSearchResult

    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = register(client)
        gap, _ = generate_valid(app, client, headers)
        app.state.search_service.search = AsyncMock(
            return_value=FederatedSearchResult(
                papers=[PaperRecord(title=f"Unreviewed adjacent study {i}") for i in range(3)]
                if source_status == "ok"
                else [],
                source_status={"fixture": SourceStatus(status=source_status)},
            )
        )
        response = client.post(f"/api/gaps/{gap['id']}/challenge", headers=headers, json={})
        assert response.status_code == 200, response.text
        value = response.json()
        assert value["confidence"] == "low"
        if source_status != "ok":
            assert value["challenge_completed_at"] is None
            assert value["counter_evidence"] == []
            confirm = client.post(
                f"/api/gaps/{gap['id']}/confirm", headers=headers, json={"confirmed": True}
            )
            assert confirm.status_code == 409
        else:
            assert all(item["relationship"] == "unevaluated" for item in value["counter_evidence"])
            assert value["explanation"]["weakening_papers"] == []


def test_legacy_plan_read_is_review_only_and_cannot_advance(tmp_path):
    from research_navigator.models import PlanItem

    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = register(client)
        project = client.post(
            "/api/projects", headers=headers, json={"name": "segmentation"}
        ).json()
        with app.state.database.session() as session:
            user = session.scalar(select(User))
            plan = ResearchPlan(
                user_id=user.id,
                project_id=project["id"],
                title="Historical plan",
                objective="Unverified old conclusion",
            )
            session.add(plan)
            session.flush()
            item = PlanItem(
                plan_id=plan.id,
                user_id=user.id,
                title="Old item",
                description="Old",
                category="experiment",
                sequence=1,
            )
            session.add(item)
            session.commit()
            plan_id, item_id = plan.id, item.id
        read = client.get(f"/api/plans/{plan_id}", headers=headers)
        assert read.status_code == 200
        assert read.json()["review_required"] is True
        update = client.put(f"/api/plan-items/{item_id}", headers=headers, json={"status": "done"})
        assert update.status_code == 409


def test_missing_evidence_returns_actionable_conflict_without_writes(tmp_path):
    app = create_app(settings_for(tmp_path))
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = register(client)
        project = client.post(
            "/api/projects", headers=headers, json={"name": "图像语义分割"}
        ).json()
        papers = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "anomaly", "sources": ["fixture"], "limit": 2},
        ).json()["papers"]
        with app.state.database.session() as session:
            before = session.scalar(select(func.count()).select_from(PaperSet))
        result = client.post(
            "/api/gaps/generate",
            headers=headers,
            json={"project_id": project["id"], "paper_ids": [p["id"] for p in papers]},
        )
        assert result.status_code == 409, result.text
        assert "证据" in result.json()["detail"]["reason"]
        assert result.json()["detail"]["actions"]
        with app.state.database.session() as session:
            assert session.scalar(select(func.count()).select_from(PaperSet)) == before
            assert session.scalar(select(func.count()).select_from(GapCandidate)) == 0


@pytest.mark.parametrize("operation", ["confirm", "challenge", "plan"])
def test_legacy_candidate_cannot_advance(tmp_path, operation):
    app = create_app(settings_for(tmp_path))
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = register(client)
        project = client.post(
            "/api/projects", headers=headers, json={"name": "图像语义分割"}
        ).json()
        with app.state.database.session() as session:
            user = session.scalar(select(User))
            gap = GapCandidate(
                user_id=user.id,
                project_id=project["id"],
                gap_type="legacy",
                claim="future window warning",
                scope="segmentation",
                status="confirmed" if operation == "plan" else "pending_confirmation",
                challenge_completed_at=datetime.now(UTC),
                suggested_research_question="old unsupported question",
            )
            session.add(gap)
            session.commit()
            gap_id = gap.id
        path = "/api/plans" if operation == "plan" else f"/api/gaps/{gap_id}/{operation}"
        payload = (
            {"project_id": project["id"], "gap_id": gap_id}
            if operation == "plan"
            else {"confirmed": True}
            if operation == "confirm"
            else {}
        )
        result = client.post(path, headers=headers, json=payload)
        assert result.status_code == 409, result.text
        with app.state.database.session() as session:
            assert session.scalar(select(func.count()).select_from(ResearchPlan)) == 0
            assert session.get(GapCandidate, gap_id) is not None  # History must survive.


@pytest.mark.parametrize("operation", ["confirm", "plan"])
def test_changed_challenge_invalidates_confirmation_and_plan(tmp_path, operation):
    from unittest.mock import AsyncMock

    from research_navigator.scholarly.base import SourceStatus
    from research_navigator.scholarly.service import FederatedSearchResult

    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        headers = register(client)
        gap, payload = generate_valid(app, client, headers)
        app.state.search_service.search = AsyncMock(
            return_value=FederatedSearchResult(
                papers=[], source_status={"fixture": SourceStatus(status="ok")}
            )
        )
        assert (
            client.post(f"/api/gaps/{gap['id']}/challenge", headers=headers, json={}).status_code
            == 200
        )
        if operation == "plan":
            assert (
                client.post(
                    f"/api/gaps/{gap['id']}/confirm", headers=headers, json={"confirmed": True}
                ).status_code
                == 200
            )
        with app.state.database.session() as session:
            row = session.get(GapCandidate, gap["id"])
            row.counter_evidence_json = '[{"paper_id":999,"relationship":"refutes"}]'
            session.commit()
        path = "/api/plans" if operation == "plan" else f"/api/gaps/{gap['id']}/confirm"
        body = (
            {"project_id": payload["project_id"], "gap_id": gap["id"]}
            if operation == "plan"
            else {"confirmed": True}
        )
        result = client.post(path, headers=headers, json=body)
        assert result.status_code == 409, result.text
