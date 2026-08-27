"""Research profile and project endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.idempotency import replay_snapshot, store_snapshot
from research_navigator.models import ResearchProfile, ResearchProject, User
from research_navigator.schemas.projects import (
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ResearchProfileRead,
    ResearchProfileUpsert,
)

router = APIRouter(tags=["research"])


def _profile_read(profile: ResearchProfile) -> ResearchProfileRead:
    return ResearchProfileRead(
        id=profile.id,
        user_id=profile.user_id,
        stage=profile.stage,
        major=profile.major,
        broad_direction=profile.broad_direction,
        keywords=json.loads(profile.keywords_json),
        excluded_terms=json.loads(profile.excluded_terms_json),
        preferences=json.loads(profile.preferences_json),
        compute_constraints=profile.compute_constraints,
    )


@router.get("/research-profiles/me", response_model=ResearchProfileRead | None)
def get_profile(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> ResearchProfileRead | None:
    profile = session.scalar(select(ResearchProfile).where(ResearchProfile.user_id == user.id))
    return None if profile is None else _profile_read(profile)


@router.put("/research-profiles/me", response_model=ResearchProfileRead)
def upsert_profile(
    payload: ResearchProfileUpsert,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ResearchProfileRead:
    profile = session.scalar(select(ResearchProfile).where(ResearchProfile.user_id == user.id))
    if profile is None:
        profile = ResearchProfile(user_id=user.id)
        session.add(profile)
    profile.stage = payload.stage
    profile.major = payload.major
    profile.broad_direction = payload.broad_direction
    profile.keywords_json = json.dumps(payload.keywords, ensure_ascii=False)
    profile.excluded_terms_json = json.dumps(payload.excluded_terms, ensure_ascii=False)
    profile.preferences_json = json.dumps(payload.preferences, ensure_ascii=False)
    profile.compute_constraints = payload.compute_constraints
    session.commit()
    session.refresh(profile)
    return _profile_read(profile)


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ResearchProject | ProjectRead:
    replay = replay_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="projects.create",
        payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return ProjectRead.model_validate(replay)
    project = ResearchProject(user_id=user.id, **payload.model_dump())
    session.add(project)
    session.commit()
    session.refresh(project)
    result = ProjectRead.model_validate(project)
    store_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="projects.create",
        payload=payload.model_dump(mode="json"),
        resource_type="project",
        resource_id=project.id,
        response_snapshot=result.model_dump(mode="json"),
    )
    return result


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> list[ResearchProject]:
    return list(
        session.scalars(
            select(ResearchProject)
            .where(ResearchProject.user_id == user.id)
            .order_by(ResearchProject.updated_at.desc())
        )
    )


def _owned_project(session: Session, user_id: int, project_id: int) -> ResearchProject:
    project = session.scalar(
        select(ResearchProject).where(
            ResearchProject.id == project_id, ResearchProject.user_id == user_id
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ResearchProject:
    return _owned_project(session, user.id, project_id)


@router.put("/projects/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ResearchProject:
    project = _owned_project(session, user.id, project_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    session.commit()
    session.refresh(project)
    return project
