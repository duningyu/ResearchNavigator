from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.models import Paper, User
from research_navigator.schemas.translation import AbstractTranslationRead

router = APIRouter(tags=["translation"])


def _paper_translation(
    paper_id: int,
    request: Request,
    target_language: str,
    session: Session,
) -> AbstractTranslationRead:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    result = request.app.state.translation_service.lookup(
        paper.id, paper.abstract, target_language, session
    )
    return AbstractTranslationRead.model_validate(result.__dict__)


@router.get("/papers/{paper_id}/abstract-translation", response_model=AbstractTranslationRead)
def get_abstract_translation(
    paper_id: int, request: Request, target_language: str = "zh-CN",
    user: User = Depends(get_current_user), session: Session = Depends(get_db),
) -> AbstractTranslationRead:
    del user
    return _paper_translation(paper_id, request, target_language, session)


@router.post("/papers/{paper_id}/abstract-translation", response_model=AbstractTranslationRead)
def create_abstract_translation(
    paper_id: int, request: Request, target_language: str = "zh-CN",
    user: User = Depends(get_current_user), session: Session = Depends(get_db),
) -> AbstractTranslationRead:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    result = request.app.state.translation_service.translate(
        paper.id, paper.abstract, target_language, session
    )
    return AbstractTranslationRead.model_validate(result.__dict__)
