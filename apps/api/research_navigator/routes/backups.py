"""Administrator backup and restart-bound staged restore endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse

from research_navigator.backups.service import create_backup, list_backups, stage_restore
from research_navigator.deps import ensure_public_demo_operation_allowed, get_current_user
from research_navigator.models import User
from research_navigator.schemas.backups import BackupRead, StageRestoreRead, StageRestoreRequest

router = APIRouter(prefix="/admin/backups", tags=["backups"])


def _admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator permission required")


@router.get("", response_model=list[BackupRead])
def backups(request: Request, user: User = Depends(get_current_user)) -> list[BackupRead]:
    _admin(user)
    return [BackupRead.model_validate(item) for item in list_backups(request.app.state.settings)]


@router.post("", response_model=BackupRead, status_code=status.HTTP_201_CREATED)
def backup(request: Request, user: User = Depends(get_current_user)) -> BackupRead:
    _admin(user)
    ensure_public_demo_operation_allowed(request)
    try:
        return BackupRead.model_validate(create_backup(request.app.state.settings))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{name}/download")
def download_backup(
    name: str, request: Request, user: User = Depends(get_current_user)
) -> FileResponse:
    _admin(user)
    ensure_public_demo_operation_allowed(request)
    path = (request.app.state.settings.backup_dir / name).resolve()
    root = request.app.state.settings.backup_dir.resolve()
    if path.parent != root or not path.is_file() or path.suffix.lower() != ".zip":
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(path, filename=path.name, media_type="application/zip")


@router.post(
    "/{name}/stage-restore", response_model=StageRestoreRead, status_code=status.HTTP_202_ACCEPTED
)
def restore(
    name: str,
    payload: StageRestoreRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> StageRestoreRead:
    _admin(user)
    ensure_public_demo_operation_allowed(request)
    if not payload.confirm_restore:
        raise HTTPException(status_code=409, detail="Explicit restore confirmation is required")
    try:
        result = stage_restore(request.app.state.settings, name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StageRestoreRead.model_validate(result)
