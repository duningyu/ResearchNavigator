"""Persistent SQLite worker with restart recovery and bounded job handlers."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from research_navigator.analysis.providers import build_analysis_provider
from research_navigator.analysis.service import run_paper_analysis
from research_navigator.config import Settings
from research_navigator.db import Database
from research_navigator.evidence.backfill import execute_abstract_backfill
from research_navigator.evidence.workflow import execute_evidence_workflow
from research_navigator.gaps.service import run_gap_challenge
from research_navigator.models import Job, JobEvent
from research_navigator.open_access import build_open_access_resolver, build_pdf_fetcher
from research_navigator.recommendations.service import refresh_recommendations
from research_navigator.scholarly.service import build_search_service


def _event(
    session: Any,
    job: Job,
    event_type: str,
    detail: dict[str, object] | None = None,
) -> None:
    session.add(
        JobEvent(
            job_id=job.id,
            user_id=job.user_id,
            event_type=event_type,
            detail_json=json.dumps(detail or {}, ensure_ascii=False),
        )
    )


def recover_interrupted_jobs(database: Database) -> int:
    recovered = 0
    with database.session() as session:
        rows = list(session.scalars(select(Job).where(Job.status == "running")))
        for row in rows:
            row.status = "pending"
            row.locked_by = None
            _event(session, row, "recovered", {"reason": "worker_restart"})
            recovered += 1
        session.commit()
    return recovered


def _require_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _claim_job(session: Session, *, worker_id: str) -> Job | None:
    """Claim the oldest pending job with one database transition.

    Selecting a pending row and committing it later permits two workers to select
    the same job. The conditional UPDATE makes the status transition the claim
    point; a second caller therefore observes zero affected rows.
    """
    now = datetime.now(UTC)
    job_id = session.scalar(
        update(Job)
        .where(
            Job.id
            == select(Job.id)
            .where(Job.status == "pending")
            .order_by(Job.created_at, Job.id)
            .limit(1)
            .scalar_subquery(),
            Job.status == "pending",
        )
        .values(
            status="running",
            locked_by=worker_id,
            started_at=now,
            attempt_count=Job.attempt_count + 1,
        )
        .returning(Job.id)
    )
    if job_id is None:
        return None
    job = session.get(Job, job_id)
    if job is None:
        raise RuntimeError("Claimed job disappeared")
    _event(session, job, "started", {"worker_id": worker_id})
    session.commit()
    return job


def _execute_job(session: Any, job: Job, *, settings: Settings) -> dict[str, object]:
    payload = json.loads(job.payload_json)
    if not isinstance(payload, dict):
        raise ValueError("Job payload must be an object")
    if job.job_type == "noop":
        return {"echo": payload}
    if job.job_type == "paper_analysis":
        paper_id = _require_int(payload, "paper_id")
        project_value = payload.get("project_id", job.project_id)
        project_id = None if project_value is None else int(project_value)
        analysis_row = run_paper_analysis(
            session,
            user_id=job.user_id,
            paper_id=paper_id,
            project_id=project_id,
        )
        return {
            "analysis_id": analysis_row.id,
            "paper_id": analysis_row.paper_id,
            "project_id": analysis_row.project_id,
            "evidence_level": analysis_row.evidence_level,
        }
    if job.job_type == "recommendation_refresh":
        project_value = payload.get("project_id", job.project_id)
        project_id = None if project_value is None else int(project_value)
        limit = int(payload.get("limit", 20))
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        rows = refresh_recommendations(
            session,
            user_id=job.user_id,
            project_id=project_id,
            limit=limit,
        )
        return {
            "project_id": project_id,
            "recommendation_count": len(rows),
            "recommendation_ids": [row.id for row in rows],
        }
    if job.job_type == "abstract_provenance_backfill_v1":
        execution = asyncio.run(
            execute_abstract_backfill(
                session,
                job_id=job.id,
                search_service=build_search_service(settings),
            )
        )
        result = dict(execution.result)
        result["__terminal_status"] = execution.terminal_status
        return result
    if job.job_type == "evidence_workflow_v1":
        execution = asyncio.run(
            execute_evidence_workflow(
                session,
                settings=settings,
                job_id=job.id,
                search_service=build_search_service(settings),
                oa_resolver=build_open_access_resolver(settings),
                pdf_fetcher=build_pdf_fetcher(settings),
                analysis_provider=build_analysis_provider(settings),
                prompt_version=settings.analysis_prompt_version,
            )
        )
        result = dict(execution.result)
        result["__terminal_status"] = execution.terminal_status
        return result
    if job.job_type == "gap_challenge":
        gap_id = _require_int(payload, "gap_id")
        raw_terms = payload.get("additional_terms", [])
        if not isinstance(raw_terms, list) or not all(isinstance(term, str) for term in raw_terms):
            raise ValueError("additional_terms must be a list of strings")
        gap_row = asyncio.run(
            run_gap_challenge(
                session,
                user_id=job.user_id,
                gap_id=gap_id,
                additional_terms=raw_terms,
                search_service=build_search_service(settings),
            )
        )
        queries = json.loads(gap_row.challenge_queries_json)
        counter = json.loads(gap_row.counter_evidence_json)
        return {
            "gap_id": gap_row.id,
            "gap_status": gap_row.status,
            "challenge_query_count": len(queries),
            "counter_evidence_count": len(counter),
        }
    raise RuntimeError(f"Unsupported job type: {job.job_type!r}")


def run_once(
    database: Database,
    *,
    worker_id: str | None = None,
    settings: Settings | None = None,
) -> int | None:
    identity = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    resolved_settings = settings or Settings.from_env()
    with database.session() as session:
        job = _claim_job(session, worker_id=identity)
        if job is None:
            return None

        try:
            result = _execute_job(session, job, settings=resolved_settings)
            terminal_status = str(result.pop("__terminal_status", "succeeded"))
            if terminal_status not in {"succeeded", "partial", "cancelled"}:
                raise ValueError(f"Unsupported terminal status: {terminal_status}")
            job.result_json = json.dumps(result, ensure_ascii=False)
            job.status = terminal_status
            job.finished_at = datetime.now(UTC)
            job.error = None
            _event(session, job, terminal_status, result)
        except Exception as exc:
            job.error = f"{type(exc).__name__}: {exc}"
            if job.attempt_count < job.max_attempts:
                job.status = "pending"
                _event(session, job, "retry_scheduled", {"error": job.error})
            else:
                job.status = "failed"
                job.finished_at = datetime.now(UTC)
                _event(session, job, "failed", {"error": job.error})
        finally:
            job.locked_by = None
            session.commit()
        return job.id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.ensure_directories()
    database = Database.from_url(settings.database_url)
    database.init()
    recover_interrupted_jobs(database)
    if args.once:
        run_once(database, settings=settings)
        return
    while True:
        try:
            processed = run_once(database, settings=settings)
        except OperationalError as exc:
            # Concurrent API write transactions can transiently exceed SQLite's
            # busy timeout ("database is locked"); one failed poll must not
            # kill the worker process.
            print(f"[worker] transient database error, will retry: {exc}",
                  file=sys.stderr, flush=True)
            time.sleep(max(args.poll_seconds, 1.0))
            continue
        if processed is None:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
