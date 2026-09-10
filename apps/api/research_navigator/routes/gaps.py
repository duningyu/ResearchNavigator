"""Evidence-bounded candidate research-gap workflow."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.gaps.candidate import make_gap_candidate
from research_navigator.gaps.eligibility import EvidenceGateBlocked
from research_navigator.gaps.guard import StaleGapEvidence, assert_current_gap, context_fingerprint
from research_navigator.gaps.matrix import build_evidence_matrix
from research_navigator.gaps.service import append_gap_explanation, run_gap_challenge
from research_navigator.gaps.workflow import assert_confirmable
from research_navigator.idempotency import replay_snapshot, store_snapshot
from research_navigator.models import (
    AgentRun,
    GapCandidate,
    GapEvidence,
    GapExplanation,
    Paper,
    PaperSet,
    PaperSetItem,
    ResearchProfile,
    ResearchProject,
    User,
)
from research_navigator.schemas.gaps import (
    GapCandidateRead,
    GapChallengeRequest,
    GapConfirmRequest,
    GapGenerateRequest,
)
from research_navigator.scholarly.service import FederatedSearchService

router = APIRouter(tags=["research-gaps"])


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _owned_project(session: Session, *, user_id: int, project_id: int) -> ResearchProject:
    project = session.scalar(
        select(ResearchProject).where(
            ResearchProject.id == project_id, ResearchProject.user_id == user_id
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _owned_gap(session: Session, *, user_id: int, gap_id: int) -> GapCandidate:
    row = session.scalar(
        select(GapCandidate).where(GapCandidate.id == gap_id, GapCandidate.user_id == user_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Gap candidate not found")
    return row


def _workflow_stage(status_value: str) -> str:
    return {
        "generated": "challenge_required",
        "pending_confirmation": "awaiting_human_confirmation",
        "confirmed": "human_confirmed",
        "rejected": "human_rejected",
    }.get(status_value, status_value)


def _latest_explanation(session: Session, row: GapCandidate) -> dict[str, object] | None:
    explanation = session.scalar(
        select(GapExplanation)
        .where(GapExplanation.gap_id == row.id, GapExplanation.user_id == row.user_id)
        .order_by(GapExplanation.version.desc(), GapExplanation.id.desc())
    )
    return None if explanation is None else json.loads(explanation.explanation_json)


def _read(session: Session, row: GapCandidate) -> GapCandidateRead:
    review_reason = None
    try:
        assert_current_gap(session, row)
    except StaleGapEvidence as exc:
        review_reason = str(exc)
    return GapCandidateRead(
        review_required=review_reason is not None,
        review_reason=review_reason,
        id=row.id,
        project_id=row.project_id,
        paper_set_id=row.paper_set_id,
        direction_snapshot=json.loads(row.direction_snapshot_json),
        gap_type=row.gap_type,
        claim=row.claim,
        scope=row.scope,
        status=row.status,
        workflow_stage=_workflow_stage(row.status),
        evidence_matrix=json.loads(row.evidence_matrix_json),
        supporting_evidence=json.loads(row.supporting_evidence_json),
        adjacent_work=json.loads(row.adjacent_work_json),
        counter_evidence=json.loads(row.counter_evidence_json),
        challenge_queries=json.loads(row.challenge_queries_json),
        data_sources=json.loads(row.data_sources_json),
        coverage=json.loads(row.coverage_json),
        confidence=row.confidence,
        risk_factors=json.loads(row.risk_factors_json),
        minimal_validation=json.loads(row.minimal_validation_json),
        suggested_research_question=row.suggested_research_question,
        not_novelty_proof=row.not_novelty_proof,
        explanation=_latest_explanation(session, row),
        challenge_completed_at=row.challenge_completed_at,
        confirmed_at=row.confirmed_at,
        human_confirmation_note=row.human_confirmation_note,
        created_at=row.created_at,
    )


def _direction_snapshot(
    session: Session, user_id: int, project: ResearchProject
) -> dict[str, object]:
    profile = session.scalar(select(ResearchProfile).where(ResearchProfile.user_id == user_id))
    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "broad_direction": project.broad_direction,
        },
        "profile": None
        if profile is None
        else {
            "stage": profile.stage,
            "major": profile.major,
            "broad_direction": profile.broad_direction,
            "keywords": json.loads(profile.keywords_json),
            "excluded_terms": json.loads(profile.excluded_terms_json),
            "preferences": json.loads(profile.preferences_json),
            "compute_constraints": profile.compute_constraints,
        },
    }


def _resolve_paper_set(
    session: Session, *, user_id: int, project: ResearchProject, payload: GapGenerateRequest
) -> tuple[PaperSet, list[int]]:
    if payload.paper_set_id is not None:
        paper_set = session.scalar(
            select(PaperSet).where(PaperSet.id == payload.paper_set_id, PaperSet.user_id == user_id)
        )
        if paper_set is None:
            raise HTTPException(status_code=404, detail="Paper set not found")
        if paper_set.project_id is not None and paper_set.project_id != project.id:
            raise HTTPException(status_code=409, detail="Paper set belongs to a different project")
        items = list(
            session.scalars(
                select(PaperSetItem)
                .where(PaperSetItem.paper_set_id == paper_set.id)
                .order_by(PaperSetItem.position)
            )
        )
        paper_ids = [item.paper_id for item in items]
        if not paper_ids:
            raise HTTPException(status_code=422, detail="Paper set is empty")
        return paper_set, paper_ids

    paper_ids = list(dict.fromkeys(payload.paper_ids))
    existing_ids = set(session.scalars(select(Paper.id).where(Paper.id.in_(paper_ids))))
    if existing_ids != set(paper_ids):
        raise HTTPException(status_code=404, detail="One or more papers were not found")
    paper_set = PaperSet(
        user_id=user_id,
        project_id=project.id,
        purpose="gap",
        name=f"Gap selection · {project.name}",
        source_kind="explicit",
    )
    session.add(paper_set)
    session.flush()
    for position, paper_id in enumerate(paper_ids):
        session.add(PaperSetItem(paper_set_id=paper_set.id, paper_id=paper_id, position=position))
    return paper_set, paper_ids


@router.post("/gaps/generate", response_model=GapCandidateRead, status_code=status.HTTP_201_CREATED)
def generate_gap(
    payload: GapGenerateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> GapCandidateRead:
    replay = replay_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="gaps.generate",
        payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        existing = _owned_gap(session, user_id=user.id, gap_id=int(replay["id"]))
        try:
            assert_current_gap(session, existing)
        except StaleGapEvidence as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _read(session, existing)
    project = _owned_project(session, user_id=user.id, project_id=payload.project_id)
    paper_set, paper_ids = _resolve_paper_set(
        session, user_id=user.id, project=project, payload=payload
    )
    existing_ids = set(session.scalars(select(Paper.id).where(Paper.id.in_(paper_ids))))
    if existing_ids != set(paper_ids):
        raise HTTPException(status_code=404, detail="One or more papers were not found")
    matrix = build_evidence_matrix(
        session, user_id=user.id, project_id=project.id, paper_ids=paper_ids
    )
    direction_snapshot = _direction_snapshot(session, user.id, project)
    paper_set.direction_snapshot_json = _json(direction_snapshot)
    try:
        draft = make_gap_candidate(
            project_direction=project.broad_direction or project.name,
            paper_ids=paper_ids,
            evidence_matrix=matrix,
        )
    except EvidenceGateBlocked as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=exc.decision.model_dump(mode="json")) from exc
    draft.coverage["context_fingerprint"] = context_fingerprint(session, project, paper_ids)
    row = GapCandidate(
        user_id=user.id,
        project_id=project.id,
        paper_set_id=paper_set.id,
        direction_snapshot_json=_json(direction_snapshot),
        gap_type=draft.gap_type,
        claim=draft.claim,
        scope=draft.scope,
        status=draft.status,
        evidence_matrix_json=_json(matrix),
        supporting_evidence_json=_json(draft.supporting_evidence),
        adjacent_work_json=_json(draft.adjacent_work),
        counter_evidence_json="[]",
        challenge_queries_json="[]",
        data_sources_json="[]",
        coverage_json=_json(draft.coverage),
        confidence=draft.confidence,
        risk_factors_json=_json(draft.risk_factors),
        minimal_validation_json=_json(draft.minimal_validation),
        suggested_research_question=draft.suggested_research_question,
        not_novelty_proof=True,
    )
    session.add(row)
    session.flush()
    for paper_id in paper_ids:
        session.add(
            GapEvidence(
                gap_id=row.id,
                paper_id=paper_id,
                evidence_role="adjacent",
                rationale="Explicitly selected corpus item used to construct the evidence matrix.",
            )
        )
    append_gap_explanation(session, row=row)
    output = _read(session, row).model_dump(mode="json")
    output_hash = hashlib.sha256(_json(output).encode()).hexdigest()
    session.add(
        AgentRun(
            run_id=uuid.uuid4().hex,
            user_id=user.id,
            project_id=project.id,
            workflow_type="gap_generation",
            workflow_version="gap-workflow-v2",
            prompt_version="deterministic-gap-explainer-v2",
            status="succeeded",
            input_json=_json(payload.model_dump(mode="json")),
            output_json=_json(output),
            finished_at=datetime.now(UTC),
            output_hash=output_hash,
        )
    )
    session.commit()
    session.refresh(row)
    result = _read(session, row)
    store_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="gaps.generate",
        payload=payload.model_dump(mode="json"),
        resource_type="gap",
        resource_id=row.id,
        response_snapshot=result.model_dump(mode="json"),
    )
    return result


@router.post("/gaps/{gap_id}/challenge", response_model=GapCandidateRead)
async def challenge_gap(
    gap_id: int,
    payload: GapChallengeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> GapCandidateRead:
    service: FederatedSearchService = request.app.state.search_service
    try:
        row = await run_gap_challenge(
            session,
            user_id=user.id,
            gap_id=gap_id,
            additional_terms=payload.additional_terms,
            search_service=service,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StaleGapEvidence as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _read(session, row)


@router.post("/gaps/{gap_id}/confirm", response_model=GapCandidateRead)
def confirm_gap(
    gap_id: int,
    payload: GapConfirmRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> GapCandidateRead:
    row = _owned_gap(session, user_id=user.id, gap_id=gap_id)
    idempotency_payload = {"gap_id": gap_id, **payload.model_dump(mode="json")}
    replay = replay_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="gaps.confirm",
        payload=idempotency_payload,
    )
    if replay is not None:
        # A replay must not turn an otherwise stale confirmation into a
        # current one. Re-check the evidence context before returning the
        # original snapshot for affirmative confirmations.
        if payload.confirmed:
            try:
                assert_current_gap(session, row)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _read(session, row)

    try:
        if payload.confirmed:
            assert_current_gap(session, row)
        assert_confirmable(row.status, row.challenge_completed_at)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    row.status = "confirmed" if payload.confirmed else "rejected"
    row.confirmed_at = datetime.now(UTC)
    row.human_confirmation_note = payload.note
    session.commit()
    session.refresh(row)
    result = _read(session, row)
    store_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="gaps.confirm",
        payload=idempotency_payload,
        resource_type="gap",
        resource_id=row.id,
        response_snapshot=result.model_dump(mode="json"),
    )
    return result


@router.get("/gaps/{gap_id}", response_model=GapCandidateRead)
def get_gap(
    gap_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> GapCandidateRead:
    return _read(session, _owned_gap(session, user_id=user.id, gap_id=gap_id))


@router.get("/gaps", response_model=list[GapCandidateRead])
def list_gaps(
    project_id: int | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[GapCandidateRead]:
    stmt = select(GapCandidate).where(GapCandidate.user_id == user.id)
    if project_id is not None:
        stmt = stmt.where(GapCandidate.project_id == project_id)
    rows = list(session.scalars(stmt.order_by(GapCandidate.created_at.desc())))
    return [_read(session, row) for row in rows]
