"""Versioned evidence workflow endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.evidence.workflow import (
    TERMINAL_STATUSES,
    WORKFLOW_TYPE,
    add_event,
    execute_evidence_workflow,
    finalize_execution,
    strongest_evidence,
)
from research_navigator.models import (
    Job,
    JobEvent,
    Paper,
    PaperAnalysisRecord,
    PaperDocument,
    ResearchProject,
    User,
)
from research_navigator.schemas.evidence import (
    EvidenceWorkflowCreate,
    EvidenceWorkflowEventRead,
    EvidenceWorkflowRead,
)

router = APIRouter(tags=["evidence-workflow"])


def _owned_job(session: Session, user_id: int, job_id: int) -> Job:
    row = session.scalar(
        select(Job).where(
            Job.id == job_id,
            Job.user_id == user_id,
            Job.job_type == WORKFLOW_TYPE,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Evidence workflow not found")
    return row


def _read(session: Session, row: Job) -> EvidenceWorkflowRead:
    payload = json.loads(row.payload_json)
    paper_id = int(payload["paper_id"])
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    events = list(
        session.scalars(select(JobEvent).where(JobEvent.job_id == row.id).order_by(JobEvent.id))
    )
    result = json.loads(row.result_json)
    integrity = "not_checked"
    if row.status in {"succeeded", "partial"}:
        analysis_id = result.get("analysis_id")
        analysis = (
            session.get(PaperAnalysisRecord, analysis_id) if type(analysis_id) is int else None
        )
        valid = (
            analysis is not None
            and analysis.user_id == row.user_id
            and analysis.paper_id == paper_id
            and analysis.project_id == row.project_id
        )
        document_id = result.get("document_id")
        if document_id is not None:
            document = session.get(PaperDocument, document_id) if type(document_id) is int else None
            valid = (
                valid
                and document is not None
                and (document.user_id == row.user_id and document.paper_id == paper_id)
            )
        integrity = "verified" if valid else "missing_or_mismatched"
        if not valid:
            result = {}  # Do not expose a foreign or dangling result reference.
    return EvidenceWorkflowRead(
        id=row.id,
        paper_id=paper_id,
        project_id=row.project_id,
        status=row.status,
        payload=payload,
        result=result,
        result_integrity=integrity,
        error=row.error,
        strongest_evidence=strongest_evidence(session, user_id=row.user_id, paper=paper),
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        started_at=row.started_at,
        finished_at=row.finished_at,
        cancelled_at=row.cancelled_at,
        created_at=row.created_at,
        terminal=row.status in TERMINAL_STATUSES,
        events=[
            EvidenceWorkflowEventRead(
                id=event.id,
                event_type=event.event_type,
                detail=json.loads(event.detail_json),
                created_at=event.created_at,
            )
            for event in events
        ],
    )


@router.get("/papers/{paper_id}/evidence-workflows", response_model=list[EvidenceWorkflowRead])
def list_paper_evidence_workflows(
    paper_id: int,
    project_id: int | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[EvidenceWorkflowRead]:
    """Restore contextual progress without exposing another user's job payload."""
    if session.get(Paper, paper_id) is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    if (
        project_id is not None
        and session.scalar(
            select(ResearchProject.id).where(
                ResearchProject.id == project_id, ResearchProject.user_id == user.id
            )
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Project not found")
    rows = session.scalars(
        select(Job)
        .where(
            Job.user_id == user.id,
            Job.project_id == project_id,
            Job.job_type == WORKFLOW_TYPE,
            func.json_extract(Job.payload_json, "$.paper_id") == paper_id,
        )
        .order_by(Job.id.desc())
        .limit(20)
    )
    return [_read(session, row) for row in rows]


@router.post(
    "/papers/{paper_id}/evidence-workflows",
    response_model=EvidenceWorkflowRead,
    status_code=status.HTTP_201_CREATED,
)
def create_evidence_workflow(
    paper_id: int,
    payload: EvidenceWorkflowCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> EvidenceWorkflowRead:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    if payload.project_id is not None:
        project = session.scalar(
            select(ResearchProject).where(
                ResearchProject.id == payload.project_id,
                ResearchProject.user_id == user.id,
            )
        )
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
    body = payload.model_dump(mode="json")
    body["paper_id"] = paper_id
    row = Job(
        user_id=user.id,
        project_id=payload.project_id,
        job_type=WORKFLOW_TYPE,
        status="pending",
        payload_json=json.dumps(body, ensure_ascii=False),
        max_attempts=int(request.app.state.runtime_config.get("worker_max_attempts_default", 3)),
    )
    session.add(row)
    session.flush()
    add_event(
        session,
        row,
        "created",
        {"job_type": WORKFLOW_TYPE, "paper_id": paper_id},
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return _read(session, row)


@router.get("/evidence-workflows/{job_id}", response_model=EvidenceWorkflowRead)
def get_evidence_workflow(
    job_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> EvidenceWorkflowRead:
    return _read(session, _owned_job(session, user.id, job_id))


@router.post("/evidence-workflows/{job_id}/run", response_model=EvidenceWorkflowRead)
async def run_evidence_workflow(
    job_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> EvidenceWorkflowRead:
    row = _owned_job(session, user.id, job_id)
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending workflows can be run")
    row.status = "running"
    row.started_at = datetime.now(UTC)
    row.attempt_count += 1
    add_event(session, row, "started", {"executor": "local"}, commit=False)
    session.commit()
    try:
        execution = await execute_evidence_workflow(
            session,
            settings=request.app.state.settings,
            job_id=row.id,
            search_service=request.app.state.search_service,
            oa_resolver=request.app.state.oa_resolver,
            pdf_fetcher=request.app.state.pdf_fetcher,
            analysis_provider=request.app.state.analysis_provider,
            prompt_version=request.app.state.settings.analysis_prompt_version,
            storage=request.app.state.storage,
        )
        finalize_execution(session, row, execution)
    except Exception as exc:
        row.error = f"{type(exc).__name__}: {exc}"
        row.status = "failed"
        row.finished_at = datetime.now(UTC)
        add_event(session, row, "failed", {"error": row.error}, commit=False)
        session.commit()
        raise HTTPException(status_code=500, detail=row.error) from exc
    return _read(session, row)


@router.post("/evidence-workflows/{job_id}/cancel", response_model=EvidenceWorkflowRead)
def cancel_evidence_workflow(
    job_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> EvidenceWorkflowRead:
    row = _owned_job(session, user.id, job_id)
    if row.status not in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="Only pending or running jobs can be cancelled")
    row.status = "cancelled"
    row.cancelled_at = datetime.now(UTC)
    row.finished_at = row.cancelled_at
    add_event(session, row, "cancelled", {}, commit=False)
    session.commit()
    session.refresh(row)
    return _read(session, row)
