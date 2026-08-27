"""Deterministic, blinded evaluation workflow and bounded aggregation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.models import (
    EvaluationAssignment,
    EvaluationRating,
    EvaluationResult,
    EvaluationStudy,
    EvaluationTask,
    User,
    utcnow,
)
from research_navigator.schemas.evaluations import EvaluationStudyCreate

SIMULATED_BOUNDARY = (
    "Simulated or developer ratings are workflow evidence only and are not real expert validation."
)
REAL_RESULTS_BOUNDARY = (
    "Results are available from self-declared non-simulated reviewers; reviewer credentials and "
    "external study validity still require independent verification."
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def create_study(
    session: Session, *, owner_user_id: int, payload: EvaluationStudyCreate
) -> EvaluationStudy:
    task_keys = [item.task_key for item in payload.tasks]
    if len(task_keys) != len(set(task_keys)):
        raise ValueError("task_key values must be unique within a study")
    positions = [item.position for item in payload.tasks]
    if len(positions) != len(set(positions)):
        raise ValueError("task positions must be unique within a study")
    protocol = dict(payload.protocol)
    protocol.setdefault("minimum_real_experts", 2)
    minimum = protocol.get("minimum_real_experts")
    if not isinstance(minimum, int) or minimum < 1:
        raise ValueError("minimum_real_experts must be a positive integer")
    study = EvaluationStudy(
        owner_user_id=owner_user_id,
        name=payload.name.strip(),
        description=payload.description,
        status="draft",
        study_version=payload.study_version,
        expert_outcome_validation="awaiting_real_experts",
        randomized_seed=payload.randomized_seed,
        protocol_json=_canonical_json(protocol),
    )
    session.add(study)
    session.flush()
    for item in sorted(payload.tasks, key=lambda row: (row.position, row.task_key)):
        session.add(
            EvaluationTask(
                study_id=study.id,
                task_key=item.task_key,
                paper_id=item.paper_id,
                baseline_payload_json=_canonical_json(item.baseline_payload),
                candidate_payload_json=_canonical_json(item.candidate_payload),
                position=item.position,
            )
        )
    session.flush()
    return study


def freeze_study(session: Session, study: EvaluationStudy) -> EvaluationStudy:
    if study.status == "frozen":
        return study
    if study.status != "draft":
        raise ValueError("Only draft studies can be frozen")
    tasks = list(
        session.scalars(
            select(EvaluationTask)
            .where(EvaluationTask.study_id == study.id)
            .order_by(EvaluationTask.position, EvaluationTask.task_key)
        )
    )
    if not tasks:
        raise ValueError("A study must contain at least one task")
    contract = {
        "study_version": study.study_version,
        "protocol": json.loads(study.protocol_json),
        "tasks": [
            {
                "task_key": task.task_key,
                "paper_id": task.paper_id,
                "position": task.position,
                "baseline": json.loads(task.baseline_payload_json),
                "candidate": json.loads(task.candidate_payload_json),
            }
            for task in tasks
        ],
    }
    study.frozen_input_hash = hashlib.sha256(_canonical_json(contract).encode("utf-8")).hexdigest()
    study.status = "frozen"
    session.flush()
    return study


def _blind_mapping(study: EvaluationStudy, task: EvaluationTask) -> list[dict[str, str]]:
    digest = hashlib.sha256(
        f"{study.randomized_seed}:{task.task_key}:{study.frozen_input_hash}".encode("utf-8")
    ).digest()
    sources = ["baseline", "candidate"] if digest[0] % 2 == 0 else ["candidate", "baseline"]
    return [
        {"label": "A", "source": sources[0]},
        {"label": "B", "source": sources[1]},
    ]


def assign_study(
    session: Session,
    *,
    study: EvaluationStudy,
    expert_user_id: int,
    is_simulated: bool,
    task_ids: list[int] | None,
) -> list[EvaluationAssignment]:
    if study.status not in {"frozen", "collecting", "results_available"}:
        raise RuntimeError("Study must be frozen before assignments are created")
    expert = session.get(User, expert_user_id)
    if expert is None or not expert.is_active:
        raise LookupError("Expert user not found")
    query = select(EvaluationTask).where(EvaluationTask.study_id == study.id)
    if task_ids is not None:
        unique = sorted(set(task_ids))
        query = query.where(EvaluationTask.id.in_(unique))
    tasks = list(session.scalars(query.order_by(EvaluationTask.position, EvaluationTask.id)))
    if not tasks:
        raise ValueError("No study tasks matched the assignment request")
    if task_ids is not None and len(tasks) != len(set(task_ids)):
        raise LookupError("One or more tasks do not belong to this study")
    created: list[EvaluationAssignment] = []
    for task in tasks:
        existing = session.scalar(
            select(EvaluationAssignment).where(
                EvaluationAssignment.task_id == task.id,
                EvaluationAssignment.expert_user_id == expert_user_id,
            )
        )
        if existing is not None:
            if existing.is_simulated != is_simulated:
                raise ValueError("Existing assignment simulation classification cannot be changed")
            created.append(existing)
            continue
        row = EvaluationAssignment(
            study_id=study.id,
            task_id=task.id,
            expert_user_id=expert_user_id,
            blind_order_json=_canonical_json(_blind_mapping(study, task)),
            status="assigned",
            is_simulated=is_simulated,
        )
        session.add(row)
        session.flush()
        created.append(row)
    if study.status == "frozen":
        study.status = "collecting"
    session.flush()
    return created


def start_assignment(assignment: EvaluationAssignment) -> EvaluationAssignment:
    if assignment.status == "completed":
        return assignment
    if assignment.status not in {"assigned", "started"}:
        raise ValueError("Assignment cannot be started from its current status")
    if assignment.started_at is None:
        assignment.started_at = utcnow()
    assignment.status = "started"
    return assignment


def _elapsed_seconds(started_at: datetime | None) -> int:
    if started_at is None:
        raise RuntimeError("Assignment must be started before rating")
    start = started_at if started_at.tzinfo is not None else started_at.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - start).total_seconds()))


def submit_rating(
    session: Session,
    *,
    assignment: EvaluationAssignment,
    expert_user_id: int,
    values: dict[str, Any],
) -> EvaluationRating:
    if assignment.expert_user_id != expert_user_id:
        raise LookupError("Assignment not found")
    existing = session.scalar(
        select(EvaluationRating).where(EvaluationRating.assignment_id == assignment.id)
    )
    if existing is not None:
        raise ValueError("Assignment already has a rating")
    duration = _elapsed_seconds(assignment.started_at)
    rating = EvaluationRating(
        assignment_id=assignment.id,
        expert_user_id=expert_user_id,
        evidence_correctness=float(values["evidence_correctness"]),
        evidence_sufficiency=float(values["evidence_sufficiency"]),
        citation_usefulness=float(values["citation_usefulness"]),
        missing_field_correctness=float(values["missing_field_correctness"]),
        preference=str(values["preference"]),
        comments=values.get("comments"),
        duration_seconds=duration,
    )
    session.add(rating)
    assignment.status = "completed"
    assignment.completed_at = utcnow()
    session.flush()
    return rating


def _canonical_preference(
    assignment: EvaluationAssignment, displayed_preference: str
) -> str:
    if displayed_preference == "tie":
        return "tie"
    mapping = {item["label"]: item["source"] for item in json.loads(assignment.blind_order_json)}
    return str(mapping[displayed_preference])


def _agreement_by_task(
    preferences: dict[int, list[str]],
) -> float | None:
    agreements: list[float] = []
    for values in preferences.values():
        if len(values) < 2:
            continue
        pairs = 0
        equal = 0
        for index, left in enumerate(values):
            for right in values[index + 1 :]:
                pairs += 1
                equal += int(left == right)
        if pairs:
            agreements.append(equal / pairs)
    return round(mean(agreements), 6) if agreements else None


def aggregate_study_results(session: Session, study: EvaluationStudy) -> EvaluationResult:
    assignments = list(
        session.scalars(
            select(EvaluationAssignment).where(EvaluationAssignment.study_id == study.id)
        )
    )
    by_id = {row.id: row for row in assignments}
    assignment_ids = list(by_id)
    ratings = (
        list(
            session.scalars(
                select(EvaluationRating).where(
                    EvaluationRating.assignment_id.in_(assignment_ids)
                )
            )
        )
        if assignment_ids
        else []
    )
    real_ratings = [row for row in ratings if not by_id[row.assignment_id].is_simulated]
    simulated_ratings = [row for row in ratings if by_id[row.assignment_id].is_simulated]
    real_experts = {row.expert_user_id for row in real_ratings}
    simulated_experts = {row.expert_user_id for row in simulated_ratings}
    score_fields = (
        "evidence_correctness",
        "evidence_sufficiency",
        "citation_usefulness",
        "missing_field_correctness",
    )
    mean_scores = {
        field: round(mean(float(getattr(row, field)) for row in real_ratings), 6)
        for field in score_fields
        if real_ratings
    }
    preferences_by_task: dict[int, list[str]] = defaultdict(list)
    preference_counts: Counter[str] = Counter()
    task_real_experts: dict[int, set[int]] = defaultdict(set)
    for rating in real_ratings:
        assignment = by_id[rating.assignment_id]
        canonical = _canonical_preference(assignment, rating.preference)
        preferences_by_task[assignment.task_id].append(canonical)
        preference_counts[canonical] += 1
        task_real_experts[assignment.task_id].add(rating.expert_user_id)
    tasks = list(
        session.scalars(select(EvaluationTask).where(EvaluationTask.study_id == study.id))
    )
    protocol = json.loads(study.protocol_json)
    minimum = int(protocol.get("minimum_real_experts", 2))
    coverage_met = bool(tasks) and all(
        len(task_real_experts.get(task.id, set())) >= minimum for task in tasks
    )
    validation_status = (
        "real_expert_results_available" if coverage_met else "awaiting_real_experts"
    )
    metrics: dict[str, Any] = {
        "rating_count": len(real_ratings),
        "simulated_rating_count": len(simulated_ratings),
        "task_count": len(tasks),
        "minimum_real_experts": minimum,
        "task_coverage_met": coverage_met,
        "mean_scores": mean_scores,
        "preference_counts": dict(preference_counts),
        "preference_agreement": _agreement_by_task(preferences_by_task),
        "mean_duration_seconds": (
            round(mean(row.duration_seconds for row in real_ratings), 6) if real_ratings else None
        ),
    }
    result = session.scalar(
        select(EvaluationResult).where(EvaluationResult.study_id == study.id)
    )
    if result is None:
        result = EvaluationResult(study_id=study.id)
        session.add(result)
    result.metrics_json = _canonical_json(metrics)
    result.real_expert_count = len(real_experts)
    result.simulated_count = len(simulated_experts)
    result.validation_status = validation_status
    study.expert_outcome_validation = validation_status
    if coverage_met:
        study.status = "results_available"
    session.flush()
    return result
