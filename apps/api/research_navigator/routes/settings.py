"""User preference settings endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.models import User, UserSettings
from research_navigator.schemas.settings import UserSettingsRead, UserSettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


def _ensure(session: Session, user_id: int) -> UserSettings:
    row = session.scalar(select(UserSettings).where(UserSettings.user_id == user_id))
    if row is None:
        row = UserSettings(user_id=user_id)
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def _read(row: UserSettings) -> UserSettingsRead:
    return UserSettingsRead(
        default_result_count=row.default_result_count,
        default_page_size=row.default_page_size,
        preferred_sources=json.loads(row.preferred_sources_json),
        default_open_access_only=row.default_open_access_only,
        display_language=row.display_language,
        analysis_execution_preference=row.analysis_execution_preference,
    )


@router.get("/me", response_model=UserSettingsRead)
def get_settings(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> UserSettingsRead:
    return _read(_ensure(session, user.id))


@router.put("/me", response_model=UserSettingsRead)
def update_settings(
    payload: UserSettingsUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> UserSettingsRead:
    row = _ensure(session, user.id)
    row.default_result_count = payload.default_result_count
    row.default_page_size = payload.default_page_size
    row.preferred_sources_json = json.dumps(payload.preferred_sources, ensure_ascii=False)
    row.default_open_access_only = payload.default_open_access_only
    row.display_language = payload.display_language
    row.analysis_execution_preference = payload.analysis_execution_preference
    session.commit()
    session.refresh(row)
    return _read(row)
