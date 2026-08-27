from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from research_navigator.schemas.search import PaperRead


class FavoriteCreate(BaseModel):
    paper_id: int


class FavoriteRead(BaseModel):
    id: int
    paper_id: int
    created_at: datetime


class NoteCreate(BaseModel):
    paper_id: int
    content: str = Field(min_length=1, max_length=50_000)


class NoteUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=50_000)


class NoteRead(BaseModel):
    id: int
    paper_id: int
    content: str
    note_type: str
    created_at: datetime
    updated_at: datetime


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class TagRead(BaseModel):
    id: int
    name: str


class ReadingStatusUpdate(BaseModel):
    status: str = Field(pattern="^(unread|queued|reading|read|reproducing|archived)$")
    progress: int = Field(default=0, ge=0, le=100)


class ReadingStatusRead(BaseModel):
    id: int
    paper_id: int
    status: str
    progress: int
    updated_at: datetime


class LibraryItem(BaseModel):
    paper: PaperRead
    favorite: bool
    notes: list[NoteRead]
    tags: list[TagRead]
    reading_status: ReadingStatusRead | None


class LibraryResponse(BaseModel):
    items: list[LibraryItem]
