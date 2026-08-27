"""User-scoped workspace export endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.models import User
from research_navigator.schemas.workspace import WorkspaceExportRead
from research_navigator.workspace.export import build_workspace_export

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/export", response_model=WorkspaceExportRead)
def export_workspace(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> WorkspaceExportRead:
    return WorkspaceExportRead.model_validate(build_workspace_export(session, user=user))
