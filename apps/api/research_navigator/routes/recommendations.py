"""Explainable recommendation endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.models import Paper, Recommendation, User
from research_navigator.recommendations.service import refresh_recommendations
from research_navigator.schemas.recommendations import (
    RecommendationRead,
    RecommendationRefreshRequest,
)
from research_navigator.scholarly.repository import paper_to_read

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _read(session: Session, row: Recommendation) -> RecommendationRead:
    paper = session.get(Paper, row.paper_id)
    if paper is None:
        raise RuntimeError("Recommendation references a missing paper")
    return RecommendationRead(
        id=row.id,
        project_id=row.project_id,
        category=row.category,
        score=row.score,
        reason=row.reason,
        evidence=json.loads(row.evidence_json),
        recommendation_version=row.recommendation_version,
        paper=paper_to_read(session, paper),
        created_at=row.created_at,
    )


@router.get("", response_model=list[RecommendationRead])
def list_recommendations(
    project_id: int | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[RecommendationRead]:
    rows = list(
        session.scalars(
            select(Recommendation)
            .where(
                Recommendation.user_id == user.id,
                Recommendation.project_id == project_id,
            )
            .order_by(Recommendation.score.desc(), Recommendation.id)
        )
    )
    return [_read(session, row) for row in rows]


@router.post("/refresh", response_model=list[RecommendationRead])
def refresh(
    payload: RecommendationRefreshRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[RecommendationRead]:
    try:
        rows = refresh_recommendations(
            session,
            user_id=user.id,
            project_id=payload.project_id,
            limit=payload.limit,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_read(session, row) for row in rows]
