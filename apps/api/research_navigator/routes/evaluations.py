"""Blind expert-evaluation API."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.evaluations.service import (
    REAL_RESULTS_BOUNDARY,
    SIMULATED_BOUNDARY,
    aggregate_study_results,
    assign_study,
    create_study,
    freeze_study,
    start_assignment,
    submit_rating,
)
from research_navigator.models import (
    EvaluationAssignment,
    EvaluationStudy,
    EvaluationTask,
    User,
)
from research_navigator.schemas.evaluations import (
    EvaluationAssignmentCreate,
    EvaluationAssignmentRead,
    EvaluationRatingCreate,
    EvaluationRatingRead,
    EvaluationResultRead,
    EvaluationStudyCreate,
    EvaluationStudyRead,
    EvaluationTaskRead,
    EvaluationVariantRead,
)

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


def _owned_study(session: Session, user_id: int, study_id: int) -> EvaluationStudy:
    study = session.scalar(
        select(EvaluationStudy).where(
            EvaluationStudy.id == study_id,
            EvaluationStudy.owner_user_id == user_id,
        )
    )
    if study is None:
        raise HTTPException(status_code=404, detail="Evaluation study not found")
    return study


def _study_read(session: Session, study: EvaluationStudy) -> EvaluationStudyRead:
    tasks = list(
        session.scalars(
            select(EvaluationTask)
            .where(EvaluationTask.study_id == study.id)
            .order_by(EvaluationTask.position, EvaluationTask.id)
        )
    )
    return EvaluationStudyRead(
        id=study.id,
        name=study.name,
        description=study.description,
        status=study.status,
        study_version=study.study_version,
        frozen_input_hash=study.frozen_input_hash,
        expert_outcome_validation=study.expert_outcome_validation,
        randomized_seed=study.randomized_seed,
        protocol=json.loads(study.protocol_json),
        tasks=[
            EvaluationTaskRead(
                id=task.id,
                task_key=task.task_key,
                paper_id=task.paper_id,
                position=task.position,
            )
            for task in tasks
        ],
    )


def _assignment_read(
    session: Session, assignment: EvaluationAssignment
) -> EvaluationAssignmentRead:
    task = session.get(EvaluationTask, assignment.task_id)
    if task is None:
        raise HTTPException(status_code=409, detail="Evaluation task is missing")
    payloads = {
        "baseline": json.loads(task.baseline_payload_json),
        "candidate": json.loads(task.candidate_payload_json),
    }
    mapping = json.loads(assignment.blind_order_json)
    return EvaluationAssignmentRead(
        id=assignment.id,
        study_id=assignment.study_id,
        task_id=assignment.task_id,
        task_key=task.task_key,
        status=assignment.status,
        is_simulated=assignment.is_simulated,
        variants=[
            EvaluationVariantRead(label=item["label"], payload=payloads[item["source"]])
            for item in mapping
        ],
        assigned_at=assignment.assigned_at,
        started_at=assignment.started_at,
        completed_at=assignment.completed_at,
    )


@router.get("/studies", response_model=list[EvaluationStudyRead])
def list_evaluation_studies(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[EvaluationStudyRead]:
    studies = list(
        session.scalars(
            select(EvaluationStudy)
            .where(EvaluationStudy.owner_user_id == user.id)
            .order_by(EvaluationStudy.created_at.desc(), EvaluationStudy.id.desc())
        )
    )
    return [_study_read(session, study) for study in studies]


@router.get("/studies/{study_id}", response_model=EvaluationStudyRead)
def get_evaluation_study(
    study_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> EvaluationStudyRead:
    return _study_read(session, _owned_study(session, user.id, study_id))


@router.post("/studies", response_model=EvaluationStudyRead, status_code=status.HTTP_201_CREATED)
def create_evaluation_study(
    payload: EvaluationStudyCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> EvaluationStudyRead:
    try:
        study = create_study(session, owner_user_id=user.id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    session.refresh(study)
    return _study_read(session, study)


@router.post("/studies/{study_id}/freeze", response_model=EvaluationStudyRead)
def freeze_evaluation_study(
    study_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> EvaluationStudyRead:
    study = _owned_study(session, user.id, study_id)
    try:
        freeze_study(session, study)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    session.refresh(study)
    return _study_read(session, study)


@router.post(
    "/studies/{study_id}/assignments",
    response_model=list[EvaluationAssignmentRead],
    status_code=status.HTTP_201_CREATED,
)
def create_evaluation_assignments(
    study_id: int,
    payload: EvaluationAssignmentCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[EvaluationAssignmentRead]:
    study = _owned_study(session, user.id, study_id)
    try:
        rows = assign_study(
            session,
            study=study,
            expert_user_id=payload.expert_user_id,
            is_simulated=payload.is_simulated,
            task_ids=payload.task_ids,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return [_assignment_read(session, row) for row in rows]


@router.get("/assignments", response_model=list[EvaluationAssignmentRead])
def list_my_evaluation_assignments(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[EvaluationAssignmentRead]:
    rows = list(
        session.scalars(
            select(EvaluationAssignment)
            .where(EvaluationAssignment.expert_user_id == user.id)
            .order_by(EvaluationAssignment.assigned_at, EvaluationAssignment.id)
        )
    )
    return [_assignment_read(session, row) for row in rows]


def _assigned_to_user(session: Session, assignment_id: int, user_id: int) -> EvaluationAssignment:
    row = session.scalar(
        select(EvaluationAssignment).where(
            EvaluationAssignment.id == assignment_id,
            EvaluationAssignment.expert_user_id == user_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Evaluation assignment not found")
    return row


@router.post("/assignments/{assignment_id}/start", response_model=EvaluationAssignmentRead)
def start_evaluation_assignment(
    assignment_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> EvaluationAssignmentRead:
    assignment = _assigned_to_user(session, assignment_id, user.id)
    try:
        start_assignment(assignment)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    session.refresh(assignment)
    return _assignment_read(session, assignment)


@router.post(
    "/assignments/{assignment_id}/ratings",
    response_model=EvaluationRatingRead,
    status_code=status.HTTP_201_CREATED,
)
def submit_evaluation_rating(
    assignment_id: int,
    payload: EvaluationRatingCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> EvaluationRatingRead:
    assignment = _assigned_to_user(session, assignment_id, user.id)
    try:
        rating = submit_rating(
            session,
            assignment=assignment,
            expert_user_id=user.id,
            values=payload.model_dump(),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    study = session.get(EvaluationStudy, assignment.study_id)
    if study is None:
        raise HTTPException(status_code=409, detail="Evaluation study is missing")
    aggregate_study_results(session, study)
    session.commit()
    session.refresh(rating)
    return EvaluationRatingRead(
        id=rating.id,
        assignment_id=rating.assignment_id,
        preference=rating.preference,
        duration_seconds=rating.duration_seconds,
        submitted_at=rating.submitted_at,
    )


@router.get("/studies/{study_id}/results", response_model=EvaluationResultRead)
def get_evaluation_results(
    study_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> EvaluationResultRead:
    study = _owned_study(session, user.id, study_id)
    result = aggregate_study_results(session, study)
    session.commit()
    return EvaluationResultRead(
        study_id=study.id,
        metrics=json.loads(result.metrics_json),
        real_expert_count=result.real_expert_count,
        simulated_count=result.simulated_count,
        validation_status=result.validation_status,
        claim_boundary=(
            REAL_RESULTS_BOUNDARY
            if result.validation_status == "real_expert_results_available"
            else SIMULATED_BOUNDARY
        ),
    )
