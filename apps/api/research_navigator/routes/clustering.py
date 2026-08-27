"""Deterministic direction-map endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.clustering.service import run_direction_clustering
from research_navigator.deps import get_current_user, get_db
from research_navigator.models import (
    DirectionCluster,
    DirectionClusterMember,
    DirectionClusterRun,
    User,
)
from research_navigator.schemas.clustering import (
    DirectionClusterCreate,
    DirectionClusterMemberRead,
    DirectionClusterRead,
    DirectionClusterRunRead,
)

router = APIRouter(tags=["direction-map"])


def _owned(session: Session, user_id: int, run_id: int) -> DirectionClusterRun:
    row = session.scalar(
        select(DirectionClusterRun).where(
            DirectionClusterRun.id == run_id,
            DirectionClusterRun.user_id == user_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Direction cluster run not found")
    return row


def _read(session: Session, run: DirectionClusterRun) -> DirectionClusterRunRead:
    clusters = list(
        session.scalars(
            select(DirectionCluster)
            .where(DirectionCluster.run_id == run.id)
            .order_by(DirectionCluster.cluster_key)
        )
    )
    members = list(
        session.scalars(
            select(DirectionClusterMember)
            .where(DirectionClusterMember.run_id == run.id)
            .order_by(DirectionClusterMember.paper_id)
        )
    )
    cluster_by_id = {row.id: row for row in clusters}
    return DirectionClusterRunRead(
        id=run.id,
        project_id=run.project_id,
        algorithm_version=run.algorithm_version,
        parameters=json.loads(run.parameters_json),
        input_hash=run.input_hash,
        status=run.status,
        disclaimer=run.disclaimer,
        clusters=[
            DirectionClusterRead(
                id=row.id,
                cluster_key=row.cluster_key,
                label=row.label,
                terms=json.loads(row.terms_json),
                evidence_distribution=json.loads(row.evidence_distribution_json),
            )
            for row in clusters
        ],
        members=[
            DirectionClusterMemberRead(
                paper_id=row.paper_id,
                cluster_id=row.cluster_id,
                cluster_key=(cluster_by_id[row.cluster_id].cluster_key if row.cluster_id else None),
                similarity=row.similarity,
                is_unclustered=row.is_unclustered,
            )
            for row in members
        ],
    )


@router.post(
    "/projects/{project_id}/direction-clusters",
    response_model=DirectionClusterRunRead,
    status_code=status.HTTP_201_CREATED,
)
def create_direction_clusters(
    project_id: int,
    payload: DirectionClusterCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> DirectionClusterRunRead:
    try:
        run = run_direction_clustering(
            session,
            user_id=user.id,
            project_id=project_id,
            paper_ids=payload.paper_ids,
            threshold=payload.threshold,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session.commit()
    session.refresh(run)
    return _read(session, run)


@router.get("/direction-clusters/{run_id}", response_model=DirectionClusterRunRead)
def get_direction_clusters(
    run_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> DirectionClusterRunRead:
    return _read(session, _owned(session, user.id, run_id))
