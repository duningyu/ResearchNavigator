from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.models import Paper, User
from research_navigator.schemas.translation import AbstractTranslationRead

router = APIRouter(tags=["translation"])


@router.get("/papers/{paper_id}/abstract-translation", response_model=AbstractTranslationRead)
def get_abstract_translation(
    paper_id: int,
    request: Request,
    target_language: str = "zh-CN",
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> AbstractTranslationRead:
    del user
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    result = request.app.state.translation_service.translate(
        paper.id, paper.abstract, target_language
    )
    return AbstractTranslationRead.model_validate(result.__dict__)
