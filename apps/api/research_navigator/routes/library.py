"""Personal paper library endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.idempotency import replay_snapshot, store_snapshot
from research_navigator.models import (
    Favorite,
    Note,
    Paper,
    PaperReadingStatus,
    PaperTag,
    Tag,
    User,
)
from research_navigator.schemas.library import (
    FavoriteCreate,
    FavoriteRead,
    LibraryItem,
    LibraryResponse,
    NoteCreate,
    NoteRead,
    NoteUpdate,
    ReadingStatusRead,
    ReadingStatusUpdate,
    TagCreate,
    TagRead,
)
from research_navigator.scholarly.repository import paper_to_read

router = APIRouter(prefix="/library", tags=["library"])


def _paper_or_404(session: Session, paper_id: int) -> Paper:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


def _note_read(note: Note) -> NoteRead:
    return NoteRead(
        id=note.id,
        paper_id=note.paper_id,
        content=note.content,
        note_type=note.note_type,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _status_read(row: PaperReadingStatus) -> ReadingStatusRead:
    return ReadingStatusRead(
        id=row.id,
        paper_id=row.paper_id,
        status=row.status,
        progress=row.progress,
        updated_at=row.updated_at,
    )


@router.post("/favorites", response_model=FavoriteRead, status_code=status.HTTP_201_CREATED)
def add_favorite(
    payload: FavoriteCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> FavoriteRead:
    replay = replay_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="library.favorite.create",
        payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return FavoriteRead.model_validate(replay)
    _paper_or_404(session, payload.paper_id)
    row = session.scalar(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.paper_id == payload.paper_id)
    )
    if row is None:
        row = Favorite(user_id=user.id, paper_id=payload.paper_id)
        session.add(row)
        session.commit()
        session.refresh(row)
    result = FavoriteRead(id=row.id, paper_id=row.paper_id, created_at=row.created_at)
    store_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="library.favorite.create",
        payload=payload.model_dump(mode="json"),
        resource_type="favorite",
        resource_id=row.id,
        response_snapshot=result.model_dump(mode="json"),
    )
    return result


@router.delete("/favorites/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(
    paper_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Response:
    row = session.scalar(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.paper_id == paper_id)
    )
    if row is not None:
        session.delete(row)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> NoteRead:
    replay = replay_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="library.note.create",
        payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return NoteRead.model_validate(replay)
    _paper_or_404(session, payload.paper_id)
    note = Note(user_id=user.id, paper_id=payload.paper_id, content=payload.content.strip())
    session.add(note)
    session.commit()
    session.refresh(note)
    result = _note_read(note)
    store_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="library.note.create",
        payload=payload.model_dump(mode="json"),
        resource_type="note",
        resource_id=note.id,
        response_snapshot=result.model_dump(mode="json"),
    )
    return result


@router.put("/notes/{note_id}", response_model=NoteRead)
def update_note(
    note_id: int,
    payload: NoteUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> NoteRead:
    note = session.scalar(select(Note).where(Note.id == note_id, Note.user_id == user.id))
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    note.content = payload.content.strip()
    session.commit()
    session.refresh(note)
    return _note_read(note)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Response:
    note = session.scalar(select(Note).where(Note.id == note_id, Note.user_id == user.id))
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    session.delete(note)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/tags", response_model=TagRead, status_code=status.HTTP_201_CREATED)
def create_tag(
    payload: TagCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> TagRead:
    replay = replay_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="library.tag.create",
        payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return TagRead.model_validate(replay)
    normalized = payload.name.strip()
    existing = session.scalar(select(Tag).where(Tag.user_id == user.id, Tag.name == normalized))
    if existing is not None:
        result = TagRead(id=existing.id, name=existing.name)
        store_snapshot(
            session,
            request=request,
            user_id=user.id,
            operation="library.tag.create",
            payload=payload.model_dump(mode="json"),
            resource_type="tag",
            resource_id=existing.id,
            response_snapshot=result.model_dump(mode="json"),
        )
        return result
    new_tag = Tag(user_id=user.id, name=normalized)
    session.add(new_tag)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        recovered_tag = session.scalar(
            select(Tag).where(Tag.user_id == user.id, Tag.name == normalized)
        )
        if recovered_tag is None:
            raise
        new_tag = recovered_tag
    session.refresh(new_tag)
    result = TagRead(id=new_tag.id, name=new_tag.name)
    store_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="library.tag.create",
        payload=payload.model_dump(mode="json"),
        resource_type="tag",
        resource_id=new_tag.id,
        response_snapshot=result.model_dump(mode="json"),
    )
    return result


@router.post("/papers/{paper_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def attach_tag(
    paper_id: int,
    tag_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Response:
    _paper_or_404(session, paper_id)
    tag = session.scalar(select(Tag).where(Tag.id == tag_id, Tag.user_id == user.id))
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    existing = session.scalar(
        select(PaperTag).where(
            PaperTag.user_id == user.id,
            PaperTag.paper_id == paper_id,
            PaperTag.tag_id == tag_id,
        )
    )
    if existing is None:
        session.add(PaperTag(user_id=user.id, paper_id=paper_id, tag_id=tag_id))
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/papers/{paper_id}/reading-status", response_model=ReadingStatusRead)
def update_reading_status(
    paper_id: int,
    payload: ReadingStatusUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ReadingStatusRead:
    _paper_or_404(session, paper_id)
    row = session.scalar(
        select(PaperReadingStatus).where(
            PaperReadingStatus.user_id == user.id, PaperReadingStatus.paper_id == paper_id
        )
    )
    if row is None:
        row = PaperReadingStatus(user_id=user.id, paper_id=paper_id)
        session.add(row)
    row.status = payload.status
    row.progress = payload.progress
    session.commit()
    session.refresh(row)
    return _status_read(row)


@router.get("", response_model=LibraryResponse)
def get_library(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> LibraryResponse:
    favorites = list(session.scalars(select(Favorite).where(Favorite.user_id == user.id)))
    notes = list(session.scalars(select(Note).where(Note.user_id == user.id)))
    statuses = list(
        session.scalars(select(PaperReadingStatus).where(PaperReadingStatus.user_id == user.id))
    )
    links = list(session.scalars(select(PaperTag).where(PaperTag.user_id == user.id)))
    paper_ids = (
        {row.paper_id for row in favorites}
        | {row.paper_id for row in notes}
        | {row.paper_id for row in statuses}
        | {row.paper_id for row in links}
    )
    if not paper_ids:
        return LibraryResponse(items=[])
    papers = list(session.scalars(select(Paper).where(Paper.id.in_(paper_ids)).order_by(Paper.id)))
    tags_by_id = {tag.id: tag for tag in session.scalars(select(Tag).where(Tag.user_id == user.id))}
    items: list[LibraryItem] = []
    favorite_ids = {row.paper_id for row in favorites}
    for paper in papers:
        reading = next((row for row in statuses if row.paper_id == paper.id), None)
        paper_notes = [_note_read(row) for row in notes if row.paper_id == paper.id]
        paper_tags = [
            TagRead(id=tags_by_id[row.tag_id].id, name=tags_by_id[row.tag_id].name)
            for row in links
            if row.paper_id == paper.id and row.tag_id in tags_by_id
        ]
        items.append(
            LibraryItem(
                paper=paper_to_read(session, paper),
                favorite=paper.id in favorite_ids,
                notes=paper_notes,
                tags=paper_tags,
                reading_status=_status_read(reading) if reading else None,
            )
        )
    return LibraryResponse(items=items)
