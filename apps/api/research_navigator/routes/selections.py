"""Explicit user-owned paper selection sets."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.idempotency import replay_snapshot, store_snapshot
from research_navigator.models import Paper, PaperSet, PaperSetItem, ResearchProject, User
from research_navigator.schemas.selections import PaperSetCreate, PaperSetRead
from research_navigator.scholarly.repository import paper_to_read

router = APIRouter(prefix="/paper-sets", tags=["paper-sets"])


def _read(session: Session, row: PaperSet) -> PaperSetRead:
    items = list(
        session.scalars(
            select(PaperSetItem)
            .where(PaperSetItem.paper_set_id == row.id)
            .order_by(PaperSetItem.position)
        )
    )
    papers_by_id = {
        paper.id: paper
        for paper in session.scalars(
            select(Paper).where(Paper.id.in_([item.paper_id for item in items]))
        )
    }
    ordered_papers = [
        papers_by_id[item.paper_id] for item in items if item.paper_id in papers_by_id
    ]
    return PaperSetRead(
        id=row.id,
        project_id=row.project_id,
        purpose=row.purpose,
        name=row.name,
        source_kind=row.source_kind,
        paper_ids=[item.paper_id for item in items],
        papers=[paper_to_read(session, paper) for paper in ordered_papers],
        created_at=row.created_at,
    )


def _owned_project(session: Session, *, user_id: int, project_id: int | None) -> None:
    if project_id is None:
        return
    if (
        session.scalar(
            select(ResearchProject.id).where(
                ResearchProject.id == project_id, ResearchProject.user_id == user_id
            )
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Project not found")


@router.post("", response_model=PaperSetRead, status_code=status.HTTP_201_CREATED)
def create_paper_set(
    payload: PaperSetCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> PaperSetRead:
    replay = replay_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="paper_sets.create",
        payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return PaperSetRead.model_validate(replay)
    _owned_project(session, user_id=user.id, project_id=payload.project_id)
    unique_ids = list(dict.fromkeys(payload.paper_ids))
    papers = list(session.scalars(select(Paper).where(Paper.id.in_(unique_ids))))
    if len(papers) != len(unique_ids):
        raise HTTPException(status_code=404, detail="One or more papers were not found")
    row = PaperSet(
        user_id=user.id,
        project_id=payload.project_id,
        purpose=payload.purpose,
        name=payload.name.strip(),
        source_kind=payload.source_kind,
    )
    session.add(row)
    session.flush()
    for position, paper_id in enumerate(unique_ids):
        session.add(PaperSetItem(paper_set_id=row.id, paper_id=paper_id, position=position))
    session.commit()
    session.refresh(row)
    result = _read(session, row)
    store_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="paper_sets.create",
        payload=payload.model_dump(mode="json"),
        resource_type="paper_set",
        resource_id=row.id,
        response_snapshot=result.model_dump(mode="json"),
    )
    return result


@router.get("", response_model=list[PaperSetRead])
def list_paper_sets(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> list[PaperSetRead]:
    rows = list(
        session.scalars(
            select(PaperSet).where(PaperSet.user_id == user.id).order_by(PaperSet.created_at.desc())
        )
    )
    return [_read(session, row) for row in rows]


@router.get("/{paper_set_id}", response_model=PaperSetRead)
def get_paper_set(
    paper_set_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> PaperSetRead:
    row = session.scalar(
        select(PaperSet).where(PaperSet.id == paper_set_id, PaperSet.user_id == user.id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Paper set not found")
    return _read(session, row)
