from __future__ import annotations

from pydantic import BaseModel


class WorkspaceExportRead(BaseModel):
    format_version: int
    exported_at: str
    user: dict[str, object]
    profile: dict[str, object] | None
    projects: list[dict[str, object]]
    library: list[dict[str, object]]
    gaps: list[dict[str, object]]
    plans: list[dict[str, object]]
    search_sessions: list[dict[str, object]]
