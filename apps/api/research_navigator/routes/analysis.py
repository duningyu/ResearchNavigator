"""Evidence-bounded paper analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.analysis.acquisition import (
    EvidenceAcquisitionError,
    acquire_paper_evidence,
)
from research_navigator.analysis.matching import WeightedScoreResult
from research_navigator.analysis.reproduction import ReproductionAssessment
from research_navigator.analysis.service import run_paper_analysis
from research_navigator.analysis.structured import PaperAnalysisOutput
from research_navigator.deps import get_current_user, get_db
from research_navigator.models import Paper, PaperAnalysisRecord, User
from research_navigator.schemas.analysis import (
    EvidenceAcquireRequest,
    EvidenceAcquisitionResponse,
    PaperAnalysisResponse,
    PaperAnalyzeRequest,
)
from research_navigator.scholarly.repository import paper_to_read
from research_navigator.scholarly.service import FederatedSearchService

router = APIRouter(tags=["analysis"])


def _paper_or_404(session: Session, paper_id: int) -> Paper:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


def _response(row: PaperAnalysisRecord) -> PaperAnalysisResponse:
    return PaperAnalysisResponse(
        id=row.id,
        paper_id=row.paper_id,
        project_id=row.project_id,
        analysis_version=row.analysis_version,
        analysis=PaperAnalysisOutput.model_validate_json(row.analysis_json),
        direction_similarity=WeightedScoreResult.model_validate_json(row.direction_similarity_json),
        reproduction_assessment=ReproductionAssessment.model_validate_json(
            row.reproduction_assessment_json
        ),
        created_at=row.created_at,
        analysis_mode=row.analysis_mode,
        provider=row.provider,
        model_name=row.model_name,
        prompt_version=row.prompt_version,
        fallback_reason=row.fallback_reason,
    )


@router.post("/papers/{paper_id}/analyze", response_model=PaperAnalysisResponse)
def analyze_paper(
    paper_id: int,
    payload: PaperAnalyzeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> PaperAnalysisResponse:
    try:
        row = run_paper_analysis(
            session,
            user_id=user.id,
            paper_id=paper_id,
            project_id=payload.project_id,
            provider_override=(
                request.app.state.analysis_provider
                if payload.provider != "deterministic"
                else None
            ),
            prompt_version=request.app.state.settings.analysis_prompt_version,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _response(row)


@router.post(
    "/papers/{paper_id}/acquire-evidence",
    response_model=EvidenceAcquisitionResponse,
)
async def acquire_evidence(
    paper_id: int,
    payload: EvidenceAcquireRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> EvidenceAcquisitionResponse:
    search_service: FederatedSearchService = request.app.state.search_service
    try:
        result = await acquire_paper_evidence(
            session,
            user_id=user.id,
            paper_id=paper_id,
            project_id=payload.project_id,
            requested_sources=payload.sources,
            search_service=search_service,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EvidenceAcquisitionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    analysis_row = session.get(PaperAnalysisRecord, result.analysis_id)
    if analysis_row is None:
        raise HTTPException(status_code=500, detail="Analysis was not persisted")
    return EvidenceAcquisitionResponse(
        run_id=result.run_id,
        outcome=result.outcome,
        evidence_level_before=result.evidence_level_before,
        evidence_level_after=result.evidence_level_after,
        queried_sources=result.queried_sources,
        source_status=result.source_status,
        paper=paper_to_read(session, result.paper),
        analysis=_response(analysis_row),
    )


@router.get("/papers/{paper_id}/analysis", response_model=PaperAnalysisResponse)
def get_latest_analysis(
    paper_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> PaperAnalysisResponse:
    _paper_or_404(session, paper_id)
    row = session.scalar(
        select(PaperAnalysisRecord)
        .where(
            PaperAnalysisRecord.paper_id == paper_id,
            PaperAnalysisRecord.user_id == user.id,
        )
        .order_by(PaperAnalysisRecord.created_at.desc(), PaperAnalysisRecord.id.desc())
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Paper analysis not found")
    return _response(row)
