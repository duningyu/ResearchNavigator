from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BackupRead(BaseModel):
    name: str
    size_bytes: int
    sha256: str
    created_at: datetime


class StageRestoreRequest(BaseModel):
    confirm_restore: bool = False


class StageRestoreRead(BaseModel):
    backup_name: str
    backup_sha256: str
    staged_at: datetime
    restart_required: bool
