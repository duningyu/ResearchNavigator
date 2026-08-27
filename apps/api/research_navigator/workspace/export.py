"""Build a user-scoped, credential-free workspace export."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.models import (
    Favorite,
    GapCandidate,
    Note,
    Paper,
    PaperReadingStatus,
    PlanItem,
    ResearchPlan,
    ResearchProfile,
    ResearchProject,
    SearchSession,
    User,
)


def _json(raw: str) -> object:
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def build_workspace_export(session: Session, *, user: User) -> dict[str, object]:
    profile = session.scalar(select(ResearchProfile).where(ResearchProfile.user_id == user.id))
    projects = list(
        session.scalars(
            select(ResearchProject)
            .where(ResearchProject.user_id == user.id)
            .order_by(ResearchProject.id)
        )
    )
    favorites = list(session.scalars(select(Favorite).where(Favorite.user_id == user.id)))
    notes = list(session.scalars(select(Note).where(Note.user_id == user.id)))
    statuses = list(
        session.scalars(select(PaperReadingStatus).where(PaperReadingStatus.user_id == user.id))
    )
    paper_ids = (
        {row.paper_id for row in favorites}
        | {row.paper_id for row in notes}
        | {row.paper_id for row in statuses}
    )
    papers = (
        {row.id: row for row in session.scalars(select(Paper).where(Paper.id.in_(paper_ids)))}
        if paper_ids
        else {}
    )
    plans = list(session.scalars(select(ResearchPlan).where(ResearchPlan.user_id == user.id)))
    gaps = list(session.scalars(select(GapCandidate).where(GapCandidate.user_id == user.id)))
    searches = list(session.scalars(select(SearchSession).where(SearchSession.user_id == user.id)))

    library = []
    for paper_id in sorted(paper_ids):
        paper = papers.get(paper_id)
        if paper is None:
            continue
        library.append(
            {
                "paper": {
                    "id": paper.id,
                    "title": paper.title,
                    "doi": paper.doi,
                    "arxiv_id": paper.arxiv_id,
                    "source_urls": _json(paper.source_urls_json),
                },
                "favorite": any(row.paper_id == paper_id for row in favorites),
                "notes": [
                    {
                        "content": row.content,
                        "note_type": row.note_type,
                        "updated_at": row.updated_at,
                    }
                    for row in notes
                    if row.paper_id == paper_id
                ],
                "reading_status": next(
                    (
                        {
                            "status": row.status,
                            "progress": row.progress,
                            "updated_at": row.updated_at,
                        }
                        for row in statuses
                        if row.paper_id == paper_id
                    ),
                    None,
                ),
            }
        )

    return {
        "format_version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "user": {"id": user.id, "email": user.email, "display_name": user.display_name},
        "profile": None
        if profile is None
        else {
            "stage": profile.stage,
            "major": profile.major,
            "broad_direction": profile.broad_direction,
            "keywords": _json(profile.keywords_json),
            "excluded_terms": _json(profile.excluded_terms_json),
            "preferences": _json(profile.preferences_json),
            "compute_constraints": profile.compute_constraints,
        },
        "projects": [
            {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "broad_direction": row.broad_direction,
                "status": row.status,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in projects
        ],
        "library": library,
        "gaps": [
            {
                "id": row.id,
                "project_id": row.project_id,
                "claim": row.claim,
                "status": row.status,
                "counter_evidence": _json(row.counter_evidence_json),
                "challenge_queries": _json(row.challenge_queries_json),
                "not_novelty_proof": row.not_novelty_proof,
            }
            for row in gaps
        ],
        "plans": [
            {
                "id": plan.id,
                "project_id": plan.project_id,
                "gap_id": plan.gap_id,
                "title": plan.title,
                "objective": plan.objective,
                "status": plan.status,
                "items": [
                    {
                        "id": item.id,
                        "category": item.category,
                        "title": item.title,
                        "description": item.description,
                        "sequence": item.sequence,
                        "status": item.status,
                        "notes": item.notes,
                    }
                    for item in session.scalars(
                        select(PlanItem)
                        .where(PlanItem.plan_id == plan.id, PlanItem.user_id == user.id)
                        .order_by(PlanItem.sequence)
                    )
                ],
            }
            for plan in plans
        ],
        "search_sessions": [
            {
                "id": row.id,
                "project_id": row.project_id,
                "query": row.query,
                "filters": _json(row.filters_json),
                "source_status": _json(row.source_status_json),
                "result_ids": _json(row.result_ids_json),
                "created_at": row.created_at,
            }
            for row in searches
        ],
    }
