"""Explicit evidence-aware paper comparison endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.comparisons.service import create_comparison
from research_navigator.deps import get_current_user, get_db
from research_navigator.models import ComparisonRun, User
from research_navigator.schemas.comparisons import ComparisonCreate, ComparisonRead

router = APIRouter(prefix="/comparisons", tags=["comparisons"])


def _read(row: ComparisonRun) -> ComparisonRead:
    matrix = json.loads(row.matrix_json)
    return ComparisonRead(
        id=row.id,
        project_id=row.project_id,
        paper_set_id=row.paper_set_id,
        direction_snapshot=json.loads(row.direction_snapshot_json),
        papers=matrix["papers"],
        rows=matrix["rows"],
        analysis_version=row.analysis_version,
        evidence_hash=row.evidence_hash,
        created_at=row.created_at,
    )


@router.post("", response_model=ComparisonRead, status_code=status.HTTP_201_CREATED)
def create(
    payload: ComparisonCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ComparisonRead:
    try:
        row = create_comparison(
            session,
            user_id=user.id,
            project_id=payload.project_id,
            paper_set_id=payload.paper_set_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _read(row)


@router.get("/{comparison_id}", response_model=ComparisonRead)
def get(
    comparison_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ComparisonRead:
    row = session.scalar(
        select(ComparisonRun).where(
            ComparisonRun.id == comparison_id, ComparisonRun.user_id == user.id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return _read(row)
