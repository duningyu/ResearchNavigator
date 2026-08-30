"""Persistent jobs and scholarly-source health endpoints."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.config import Settings
from research_navigator.deps import ensure_public_demo_operation_allowed, get_current_user, get_db
from research_navigator.idempotency import replay_snapshot, store_snapshot
from research_navigator.models import Job, JobEvent, ResearchProject, User
from research_navigator.schemas.jobs import JobCreate, JobEventRead, JobRead, SourceHealthRead
from research_navigator.schemas.settings import AdminConfigStatus, AdminRuntimeConfig
from research_navigator.scholarly.base import SourceStatus
from research_navigator.scholarly.runtime import SourceRuntimeRepository

router = APIRouter(tags=["system"])


@router.get("/admin/config-status", response_model=AdminConfigStatus)
def admin_config_status(
    request: Request, user: User = Depends(get_current_user)
) -> AdminConfigStatus:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator permission required")
    settings: Settings = request.app.state.settings
    return AdminConfigStatus(
        semantic_scholar_key_configured=bool(settings.semantic_scholar_api_key),
        openalex_api_key_configured=bool(settings.openalex_api_key),
        llm_key_configured=bool(settings.llm_api_key),
        analysis_provider=settings.analysis_provider,
        analysis_prompt_version=settings.analysis_prompt_version,
    )


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator permission required")


@router.get("/admin/runtime-config", response_model=AdminRuntimeConfig)
def get_admin_runtime_config(
    request: Request, user: User = Depends(get_current_user)
) -> AdminRuntimeConfig:
    _require_admin(user)
    return AdminRuntimeConfig.model_validate(request.app.state.runtime_config)


@router.put("/admin/runtime-config", response_model=AdminRuntimeConfig)
def update_admin_runtime_config(
    payload: AdminRuntimeConfig, request: Request, user: User = Depends(get_current_user)
) -> AdminRuntimeConfig:
    _require_admin(user)
    ensure_public_demo_operation_allowed(request)
    values = payload.model_dump()
    request.app.state.runtime_config = values
    config_path = request.app.state.settings.data_dir / "admin_runtime_config.json"
    config_path.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _job_read(row: Job) -> JobRead:
    return JobRead(
        id=row.id,
        project_id=row.project_id,
        job_type=row.job_type,
        status=row.status,
        payload=json.loads(row.payload_json),
        result=json.loads(row.result_json),
        error=row.error,
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        started_at=row.started_at,
        finished_at=row.finished_at,
        cancelled_at=row.cancelled_at,
        created_at=row.created_at,
        terminal=row.status in {"succeeded", "partial", "failed", "cancelled"},
    )


def _owned_job(session: Session, user_id: int, job_id: int) -> Job:
    row = session.scalar(select(Job).where(Job.id == job_id, Job.user_id == user_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return row


@router.post("/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> JobRead:
    replay = replay_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="jobs.create",
        payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return JobRead.model_validate(replay)
    if payload.project_id is not None:
        project = session.scalar(
            select(ResearchProject).where(
                ResearchProject.id == payload.project_id,
                ResearchProject.user_id == user.id,
            )
        )
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
    allowed = {"noop", "paper_analysis", "gap_challenge", "recommendation_refresh"}
    if payload.job_type not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported job type")
    row = Job(
        user_id=user.id,
        project_id=payload.project_id,
        job_type=payload.job_type,
        payload_json=json.dumps(payload.payload, ensure_ascii=False),
        status="pending",
        max_attempts=int(request.app.state.runtime_config.get("worker_max_attempts_default", 3)),
    )
    session.add(row)
    session.flush()
    session.add(
        JobEvent(
            job_id=row.id,
            user_id=user.id,
            event_type="created",
            detail_json=json.dumps({"job_type": row.job_type}),
        )
    )
    session.commit()
    session.refresh(row)
    result = _job_read(row)
    store_snapshot(
        session,
        request=request,
        user_id=user.id,
        operation="jobs.create",
        payload=payload.model_dump(mode="json"),
        resource_type="job",
        resource_id=row.id,
        response_snapshot=result.model_dump(mode="json"),
    )
    return result


@router.get("/jobs", response_model=list[JobRead])
def list_jobs(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> list[JobRead]:
    rows = list(
        session.scalars(
            select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc(), Job.id.desc())
        )
    )
    return [_job_read(row) for row in rows]


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(
    job_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> JobRead:
    return _job_read(_owned_job(session, user.id, job_id))


@router.post("/jobs/{job_id}/cancel", response_model=JobRead)
def cancel_job(
    job_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> JobRead:
    row = _owned_job(session, user.id, job_id)
    if row.status not in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="Only pending or running jobs can be cancelled")
    row.status = "cancelled"
    row.cancelled_at = datetime.now(UTC)
    session.add(
        JobEvent(
            job_id=row.id,
            user_id=user.id,
            event_type="cancelled",
            detail_json="{}",
        )
    )
    session.commit()
    session.refresh(row)
    return _job_read(row)


@router.get("/jobs/{job_id}/events", response_model=list[JobEventRead])
def get_job_events(
    job_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[JobEventRead]:
    _owned_job(session, user.id, job_id)
    rows = list(
        session.scalars(
            select(JobEvent)
            .where(JobEvent.job_id == job_id, JobEvent.user_id == user.id)
            .order_by(JobEvent.id)
        )
    )
    return [
        JobEventRead(
            id=row.id,
            event_type=row.event_type,
            detail=json.loads(row.detail_json),
            created_at=row.created_at,
        )
        for row in rows
    ]


def _source_flags(settings: Settings) -> dict[str, tuple[bool, bool, str | None]]:
    return {
        "fixture": (settings.enable_fixture_source, True, "offline fixture; never real evidence"),
        "openalex": (settings.enable_openalex, True, None),
        "crossref": (settings.enable_crossref, True, None),
        "arxiv": (settings.enable_arxiv, True, None),
        "semantic_scholar": (
            settings.enable_semantic_scholar,
            bool(settings.semantic_scholar_api_key),
            "API key optional for basic access; configured state reflects local key only",
        ),
        "unpaywall": (
            False,
            bool(settings.unpaywall_email),
            "adapter reserved; not implemented in this package version",
        ),
        "web_of_science": (False, False, "requires licensed credentials; adapter not implemented"),
        "science_direct": (
            False,
            False,
            "requires licensed Elsevier credentials; adapter not implemented",
        ),
    }


@router.get("/sources/status", response_model=list[SourceHealthRead])
async def list_source_status(
    request: Request,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[SourceHealthRead]:
    now = datetime.now(UTC)
    adapters = request.app.state.search_service.adapters
    runtime = SourceRuntimeRepository(session)
    rows: list[SourceHealthRead] = []
    for name, (enabled, configured, detail) in _source_flags(request.app.state.settings).items():
        blocked = runtime.before_call(name, now=now) if enabled else None
        if blocked is not None:
            source_status = blocked.status
            source_detail = blocked.detail or detail
            source_metadata = dict(blocked.metadata)
            checked_at = blocked.checked_at
        elif enabled and name in adapters:
            try:
                health = await asyncio.wait_for(
                    adapters[name].health(),
                    timeout=float(
                        request.app.state.runtime_config.get("source_health_timeout_seconds", 5.0)
                    ),
                )
                runtime.after_call(name, health, now=now)
                source_status = health.status
                source_detail = health.detail or detail
                source_metadata = dict(health.metadata)
                checked_at = health.checked_at
            except Exception as exc:
                source_status = "error"
                source_detail = f"{type(exc).__name__}: {exc}"
                source_metadata = {}
                checked_at = now
        elif enabled and not configured:
            source_status = "not_configured"
            source_detail = detail
            source_metadata = {}
            checked_at = now
        else:
            source_status = "disabled" if not enabled else "not_configured"
            source_detail = detail
            source_metadata = {}
            checked_at = now
        state = runtime.get(name)
        rows.append(
            SourceHealthRead(
                name=name,
                status=source_status,
                enabled=enabled,
                configured=configured,
                detail=source_detail,
                checked_at=checked_at,
                cooldown_until=state.cooldown_until if state is not None else None,
                metadata=source_metadata,
            )
        )
    session.commit()
    return rows


@router.post("/sources/{source_name}/test", response_model=SourceHealthRead)
async def test_source(
    source_name: str,
    request: Request,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> SourceHealthRead:
    flags = _source_flags(request.app.state.settings)
    if source_name not in flags:
        raise HTTPException(status_code=404, detail="Unknown source")
    enabled, configured, detail = flags[source_name]
    adapter = request.app.state.search_service.adapters.get(source_name)
    runtime = SourceRuntimeRepository(session)
    now = datetime.now(UTC)
    blocked = runtime.before_call(source_name, now=now) if enabled else None
    if blocked is not None:
        state = runtime.get(source_name)
        return SourceHealthRead(
            name=source_name,
            status=blocked.status,
            enabled=enabled,
            configured=configured,
            detail=blocked.detail or detail,
            checked_at=blocked.checked_at,
            cooldown_until=state.cooldown_until if state is not None else None,
            metadata=blocked.metadata,
        )
    if not enabled or adapter is None:
        return SourceHealthRead(
            name=source_name,
            status="disabled" if not enabled else "not_configured",
            enabled=enabled,
            configured=configured,
            detail=detail,
            checked_at=now,
        )
    try:
        health = await asyncio.wait_for(
            adapter.health(),
            timeout=float(
                request.app.state.runtime_config.get("source_health_timeout_seconds", 5.0)
            ),
        )
        state = runtime.after_call(source_name, health, now=now)
        session.commit()
        return SourceHealthRead(
            name=source_name,
            status=health.status,
            enabled=True,
            configured=configured,
            detail=health.detail or detail,
            checked_at=health.checked_at,
            cooldown_until=state.cooldown_until,
            metadata=health.metadata,
        )
    except Exception as exc:
        source_status = SourceStatus(
            status="error", detail=f"{type(exc).__name__}: {exc}", checked_at=now
        )
        state = runtime.after_call(source_name, source_status, now=now)
        session.commit()
        return SourceHealthRead(
            name=source_name,
            status="error",
            enabled=True,
            configured=configured,
            detail=source_status.detail,
            checked_at=now,
            cooldown_until=state.cooldown_until,
            metadata=source_status.metadata,
        )
