"""Editable research plan endpoints."""

from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.gaps.guard import StaleGapEvidence, assert_current_gap
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
        purpose=row.purpose,
        expected_output=row.expected_output,
        created_at=row.created_at,
    )


def _plan_read(session: Session, row: ResearchPlan) -> ResearchPlanRead:
    review_reason = _review_reason(session, row)
    items = list(
        session.scalars(
            select(PlanItem).where(PlanItem.plan_id == row.id).order_by(PlanItem.sequence)
        )
    )
    return ResearchPlanRead(
        review_required=review_reason is not None,
        review_reason=review_reason,
        id=row.id,
        project_id=row.project_id,
        gap_id=row.gap_id,
        plan_kind=cast(
            "Literal['reading', 'exploration', 'confirmed_gap', 'manual']", row.plan_kind
        ),
        title=row.title,
        objective=row.objective,
        status=row.status,
        items=[_item_read(item) for item in items],
        created_at=row.created_at,
    )


def _review_reason(session: Session, row: ResearchPlan) -> str | None:
    if row.gap_id is None:
        if row.plan_kind == "reading":
            return None
        return "此计划未关联已确认研究缺口，仅可回顾，需人工核验后再推进。"
    gap = session.get(GapCandidate, row.gap_id) if row.gap_id else None
    if (
        gap is None
        or gap.user_id != row.user_id
        or gap.project_id != row.project_id
        or gap.status != "confirmed"
    ):
        return "此计划的研究依据需重新核验，旧记录仅供回顾。"
    try:
        assert_current_gap(session, gap)
    except StaleGapEvidence as exc:
        return str(exc)
    return None


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
    project = session.scalar(
        select(ResearchProject).where(
            ResearchProject.id == payload.project_id, ResearchProject.user_id == user.id
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    plan_kind = payload.plan_kind or ("confirmed_gap" if payload.gap_id is not None else "reading")
    gap = None
    if plan_kind == "confirmed_gap" and payload.gap_id is None:
        raise HTTPException(status_code=422, detail="confirmed_gap plans require a gap candidate")
    if payload.gap_id is not None:
        gap = session.scalar(
            select(GapCandidate).where(
                GapCandidate.id == payload.gap_id,
                GapCandidate.user_id == user.id,
                GapCandidate.project_id == project.id,
            )
        )
        if gap is None:
            raise HTTPException(status_code=404, detail="Gap candidate not found")
        try:
            assert_current_gap(session, gap)
        except StaleGapEvidence as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if gap.status != "confirmed":
            raise HTTPException(
                status_code=409, detail="Only a human-confirmed gap can create a plan"
            )
    if replay is not None:
        return _plan_read(session, _owned_plan(session, user_id=user.id, plan_id=int(replay["id"])))
    row = ResearchPlan(
        user_id=user.id,
        project_id=project.id,
        gap_id=gap.id if gap else None,
        plan_kind=plan_kind,
        title=payload.title
        or (f"研究计划：{gap.suggested_research_question[:160]}" if gap else "阅读与验证计划"),
        objective=payload.objective
        or (gap.suggested_research_question if gap else "先阅读材料并记录待核验问题。"),
        status="active",
    )
    session.add(row)
    session.flush()
    for item in default_plan_items(gap.claim if gap else row.objective):
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
    plan = _owned_plan(session, user_id=user.id, plan_id=row.plan_id)
    reason = _review_reason(session, plan)
    if reason is not None:
        raise HTTPException(status_code=409, detail=reason)
    if payload.status is not None:
        row.status = payload.status
    if payload.notes is not None:
        row.notes = payload.notes
    if payload.title is not None:
        row.title = payload.title
    if payload.description is not None:
        row.description = payload.description
    if payload.purpose is not None:
        row.purpose = payload.purpose
    if payload.expected_output is not None:
        row.expected_output = payload.expected_output
    session.commit()
    session.refresh(row)
    return _item_read(row)
