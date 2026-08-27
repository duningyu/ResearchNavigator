"""Administrator-only evidence provenance backfill endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.evidence.backfill import (
    BACKFILL_JOB_TYPE,
    execute_abstract_backfill,
)
from research_navigator.evidence.workflow import add_event
from research_navigator.models import Job, User
from research_navigator.schemas.backfill import AbstractBackfillCreate, AbstractBackfillRead

router = APIRouter(tags=["backfill"])


def _admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator permission required")


def _owned(session: Session, user_id: int, job_id: int) -> Job:
    row = session.scalar(
        select(Job).where(
            Job.id == job_id,
            Job.user_id == user_id,
            Job.job_type == BACKFILL_JOB_TYPE,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Backfill job not found")
    return row


def _read(row: Job) -> AbstractBackfillRead:
    return AbstractBackfillRead(
        id=row.id,
        status=row.status,
        payload=json.loads(row.payload_json),
        result=json.loads(row.result_json),
        error=row.error,
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        cancelled_at=row.cancelled_at,
        terminal=row.status in {"succeeded", "failed", "cancelled"},
    )


@router.post(
    "/admin/backfills/abstract-provenance",
    response_model=AbstractBackfillRead,
    status_code=status.HTTP_201_CREATED,
)
def create_backfill(
    payload: AbstractBackfillCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> AbstractBackfillRead:
    _admin(user)
    body = payload.model_dump(mode="json")
    body["processed_paper_ids"] = []
    row = Job(
        user_id=user.id,
        job_type=BACKFILL_JOB_TYPE,
        status="pending",
        payload_json=json.dumps(body, ensure_ascii=False),
        max_attempts=int(request.app.state.runtime_config.get("worker_max_attempts_default", 3)),
    )
    session.add(row)
    session.flush()
    add_event(session, row, "created", {"job_type": BACKFILL_JOB_TYPE}, commit=False)
    session.commit()
    session.refresh(row)
    return _read(row)


@router.get("/admin/backfills/{job_id}", response_model=AbstractBackfillRead)
def get_backfill(
    job_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> AbstractBackfillRead:
    _admin(user)
    return _read(_owned(session, user.id, job_id))


@router.post("/admin/backfills/{job_id}/run", response_model=AbstractBackfillRead)
async def run_backfill(
    job_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> AbstractBackfillRead:
    _admin(user)
    row = _owned(session, user.id, job_id)
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending backfills can be run")
    row.status = "running"
    row.started_at = datetime.now(UTC)
    row.attempt_count += 1
    add_event(session, row, "started", {"executor": "local"}, commit=False)
    session.commit()
    try:
        execution = await execute_abstract_backfill(
            session, job_id=row.id, search_service=request.app.state.search_service
        )
        row.status = execution.terminal_status
        row.result_json = json.dumps(execution.result, ensure_ascii=False)
        row.finished_at = datetime.now(UTC)
        add_event(session, row, execution.terminal_status, execution.result, commit=False)
        session.commit()
    except Exception as exc:
        row.status = "failed"
        row.error = f"{type(exc).__name__}: {exc}"
        row.finished_at = datetime.now(UTC)
        add_event(session, row, "failed", {"error": row.error}, commit=False)
        session.commit()
        raise HTTPException(status_code=500, detail=row.error) from exc
    return _read(row)


@router.post("/admin/backfills/{job_id}/cancel", response_model=AbstractBackfillRead)
def cancel_backfill(
    job_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> AbstractBackfillRead:
    _admin(user)
    row = _owned(session, user.id, job_id)
    if row.status not in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="Only pending or running jobs can be cancelled")
    row.status = "cancelled"
    row.cancelled_at = datetime.now(UTC)
    row.finished_at = row.cancelled_at
    add_event(session, row, "cancelled", {}, commit=False)
    session.commit()
    return _read(row)
