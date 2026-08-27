"""Editable research plan endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.idempotency import replay_snapshot, store_snapshot
from research_navigator.models import GapCandidate, PlanItem, ResearchPlan, ResearchProject, User
from research_navigator.plans.service import default_plan_items
from research_navigator.schemas.plans import (
    PlanCreate,
    PlanItemRead,
    PlanItemUpdate,
    ResearchPlanRead,
)

router = APIRouter(tags=["research-plans"])


def _item_read(row: PlanItem) -> PlanItemRead:
    return PlanItemRead(
        id=row.id,
        category=row.category,
        title=row.title,
        description=row.description,
        sequence=row.sequence,
        status=row.status,
        notes=row.notes,
        created_at=row.created_at,
    )


def _plan_read(session: Session, row: ResearchPlan) -> ResearchPlanRead:
    items = list(
        session.scalars(
            select(PlanItem).where(PlanItem.plan_id == row.id).order_by(PlanItem.sequence)
        )
    )
    return ResearchPlanRead(
        id=row.id,
        project_id=row.project_id,
        gap_id=row.gap_id,
        title=row.title,
        objective=row.objective,
        status=row.status,
        items=[_item_read(item) for item in items],
        created_at=row.created_at,
    )


def _owned_plan(session: Session, *, user_id: int, plan_id: int) -> ResearchPlan:
    row = session.scalar(
        select(ResearchPlan).where(ResearchPlan.id == plan_id, ResearchPlan.user_id == user_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Research plan not found")
    return row


@router.post("/plans", response_model=ResearchPlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: PlanCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ResearchPlanRead:
    replay = replay_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="plans.create",
        payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return ResearchPlanRead.model_validate(replay)
    project = session.scalar(
        select(ResearchProject).where(
            ResearchProject.id == payload.project_id, ResearchProject.user_id == user.id
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    gap = session.scalar(
        select(GapCandidate).where(
            GapCandidate.id == payload.gap_id,
            GapCandidate.user_id == user.id,
            GapCandidate.project_id == project.id,
        )
    )
    if gap is None:
        raise HTTPException(status_code=404, detail="Gap candidate not found")
    if gap.status != "confirmed":
        raise HTTPException(status_code=409, detail="Only a human-confirmed gap can create a plan")
    row = ResearchPlan(
        user_id=user.id,
        project_id=project.id,
        gap_id=gap.id,
        title=payload.title or f"研究计划：{gap.suggested_research_question[:160]}",
        objective=gap.suggested_research_question,
        status="active",
    )
    session.add(row)
    session.flush()
    for item in default_plan_items(gap.claim):
        session.add(PlanItem(plan_id=row.id, user_id=user.id, **item))
    session.commit()
    session.refresh(row)
    result = _plan_read(session, row)
    store_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="plans.create",
        payload=payload.model_dump(mode="json"),
        resource_type="plan",
        resource_id=row.id,
        response_snapshot=result.model_dump(mode="json"),
    )
    return result


@router.get("/plans/{plan_id}", response_model=ResearchPlanRead)
def get_plan(
    plan_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ResearchPlanRead:
    return _plan_read(session, _owned_plan(session, user_id=user.id, plan_id=plan_id))


@router.get("/plans", response_model=list[ResearchPlanRead])
def list_plans(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> list[ResearchPlanRead]:
    rows = list(
        session.scalars(
            select(ResearchPlan)
            .where(ResearchPlan.user_id == user.id)
            .order_by(ResearchPlan.updated_at.desc())
        )
    )
    return [_plan_read(session, row) for row in rows]


@router.put("/plan-items/{item_id}", response_model=PlanItemRead)
def update_plan_item(
    item_id: int,
    payload: PlanItemUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> PlanItemRead:
    row = session.scalar(
        select(PlanItem).where(PlanItem.id == item_id, PlanItem.user_id == user.id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Plan item not found")
    if payload.status is not None:
        row.status = payload.status
    if payload.notes is not None:
        row.notes = payload.notes
    session.commit()
    session.refresh(row)
    return _item_read(row)
