"""Safe, explicit provenance backfill for legacy abstracts."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.analysis.acquisition import (
    _query_stages,
    _real_abstract_record,
    acquire_paper_evidence,
)
from research_navigator.models import Job, Paper, PaperSource
from research_navigator.scholarly.base import SearchRequest
from research_navigator.scholarly.service import FederatedSearchService

BACKFILL_JOB_TYPE = "abstract_provenance_backfill_v1"


@dataclass(slots=True)
class BackfillExecution:
    terminal_status: str
    result: dict[str, object]


def _verified(session: Session, paper_id: int) -> bool:
    return (
        session.scalar(
            select(PaperSource.id).where(
                PaperSource.paper_id == paper_id,
                PaperSource.provides_abstract.is_(True),
                PaperSource.is_fixture.is_(False),
            )
        )
        is not None
    )


async def _would_verify(
    paper: Paper,
    *,
    sources: list[str],
    search_service: FederatedSearchService,
) -> tuple[bool, str]:
    eligible = [
        name
        for name, adapter in search_service.adapters.items()
        if adapter.supports_evidence_acquisition
    ]
    queried = [name for name in (sources or eligible) if name in eligible]
    if not queried:
        return False, "no_eligible_source"
    any_ok = False
    for query_kind, query in _query_stages(paper):
        result = await search_service.search(
            SearchRequest(query=query, limit=10, sources=queried)
        )
        any_ok = any_ok or any(status.status == "ok" for status in result.source_status.values())
        if _real_abstract_record(paper, result.papers, query_kind) is not None:
            return True, "exact_match"
    return False, "no_matching_evidence" if any_ok else "source_unavailable"


async def execute_abstract_backfill(
    session: Session,
    *,
    job_id: int,
    search_service: FederatedSearchService,
) -> BackfillExecution:
    job = session.get(Job, job_id)
    if job is None or job.job_type != BACKFILL_JOB_TYPE:
        raise LookupError("Abstract backfill job not found")
    payload = json.loads(job.payload_json)
    dry_run = bool(payload.get("dry_run", True))
    batch_size = int(payload.get("batch_size", 25))
    sources = [str(item) for item in payload.get("sources", []) if isinstance(item, str)]
    processed_ids = set(int(item) for item in payload.get("processed_paper_ids", []))
    rows = list(
        session.scalars(
            select(Paper)
            .where(~Paper.id.in_(processed_ids) if processed_ids else Paper.id > 0)
            .order_by(Paper.id)
            .limit(batch_size)
        )
    )
    counts: Counter[str] = Counter()
    outcomes: list[dict[str, Any]] = []
    for paper in rows:
        session.refresh(job)
        if job.status == "cancelled" or job.cancelled_at is not None:
            return BackfillExecution(
                "cancelled",
                {"counts": dict(counts), "outcomes": outcomes, "dry_run": dry_run},
            )
        processed_ids.add(paper.id)
        if _verified(session, paper.id):
            category = "already_verified"
        elif dry_run:
            would_verify, reason = await _would_verify(
                paper, sources=sources, search_service=search_service
            )
            category = "would_verify" if would_verify else reason
        else:
            result = await acquire_paper_evidence(
                session,
                user_id=job.user_id,
                paper_id=paper.id,
                project_id=None,
                requested_sources=sources,
                search_service=search_service,
            )
            mapping = {
                "abstract_acquired": "verified_and_updated",
                "already_sufficient": "already_verified",
                "no_matching_evidence": "no_trusted_abstract",
                "no_eligible_source": "no_eligible_source",
                "source_unavailable": "source_unavailable",
            }
            category = mapping[result.outcome]
        counts[category] += 1
        outcomes.append({"paper_id": paper.id, "category": category})

    result_payload: dict[str, object] = {
        "dry_run": dry_run,
        "batch_size": batch_size,
        "sources": sources,
        "processed_paper_ids": sorted(processed_ids),
        "counts": dict(counts),
        "outcomes": outcomes,
        "remaining": session.scalar(
            select(Paper.id).where(~Paper.id.in_(processed_ids)).limit(1)
        )
        is not None,
    }
    return BackfillExecution("succeeded", result_payload)
