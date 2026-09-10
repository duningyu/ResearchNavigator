"""Explainable recommendation endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.models import (
    Paper,
    PaperDocument,
    PaperSource,
    Recommendation,
    ResearchProfile,
    ResearchProject,
    User,
)
from research_navigator.recommendations.service import (
    _profile_identity,
    build_reading_recommendation,
    refresh_recommendations,
)
from research_navigator.schemas.recommendations import (
    ReadingRecommendation,
    RecommendationRead,
    RecommendationRefreshRequest,
)
from research_navigator.scholarly.repository import paper_to_read

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _read(session: Session, row: Recommendation) -> RecommendationRead:
    paper = session.get(Paper, row.paper_id)
    if paper is None:
        raise RuntimeError("Recommendation references a missing paper")
    evidence = json.loads(row.evidence_json)
    reading = evidence.get("reading_recommendation")
    if not isinstance(reading, dict):
        material: PaperDocument | PaperSource | None = session.scalar(
            select(PaperDocument)
            .where(PaperDocument.paper_id == paper.id)
            .order_by(PaperDocument.created_at.desc(), PaperDocument.id.desc())
        )
        if material is None:
            material = session.scalar(
                select(PaperSource)
                .where(PaperSource.paper_id == paper.id)
                .order_by(PaperSource.created_at.desc(), PaperSource.id.desc())
            )
        reading = build_reading_recommendation(
            paper=paper,
            profile=session.scalar(
                select(ResearchProfile).where(ResearchProfile.user_id == row.user_id)
            ),
            project=session.scalar(
                select(ResearchProject).where(
                    ResearchProject.id == row.project_id,
                    ResearchProject.user_id == row.user_id,
                )
            )
            if row.project_id is not None
            else None,
            material=material,
        )
    profile = session.scalar(select(ResearchProfile).where(ResearchProfile.user_id == row.user_id))
    project = None
    if row.project_id is not None:
        project = session.scalar(
            select(ResearchProject).where(
                ResearchProject.id == row.project_id, ResearchProject.user_id == row.user_id
            )
        )
    current_profile_identity = _profile_identity(profile, project)
    if reading.get("research_profile_identity") != current_profile_identity:
        reading = {
            **reading,
            "verdict": "insufficient_evidence",
            "is_current": False,
            "invalidation_reason": "research_profile_changed",
            "missing_information": ["请刷新阅读建议以匹配当前研究方向"],
        }
    return RecommendationRead(
        id=row.id,
        project_id=row.project_id,
        category=row.category,
        score=row.score,
        reason=row.reason,
        evidence=evidence,
        recommendation_version=row.recommendation_version,
        paper=paper_to_read(session, paper),
        created_at=row.created_at,
        reading_recommendation=ReadingRecommendation.model_validate(reading),
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
