"""Resumable, evidence-bounded acquisition workflow executor."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.analysis.acquisition import (
    FULLTEXT_LEVELS,
    EvidenceAcquisitionError,
    acquire_paper_evidence,
)
from research_navigator.analysis.service import accessible_text, run_paper_analysis
from research_navigator.authors.service import refresh_author_cards
from research_navigator.config import Settings
from research_navigator.data_plane.storage import DurableStorage
from research_navigator.datasets.service import refresh_dataset_cards
from research_navigator.models import Job, JobEvent, Paper, ResearchProject
from research_navigator.open_access.base import OpenAccessResolution, PaperIdentity
from research_navigator.open_access.fetcher import PdfFetchResult
from research_navigator.open_access.ingestion import ingest_open_access_pdf
from research_navigator.scholarly.service import FederatedSearchService

WORKFLOW_TYPE = "evidence_workflow_v1"
TERMINAL_STATUSES = {"succeeded", "partial", "failed", "cancelled"}


class Resolver(Protocol):
    async def resolve(self, identity: PaperIdentity) -> OpenAccessResolution: ...


class Fetcher(Protocol):
    async def fetch(self, candidate: Any) -> PdfFetchResult: ...


@dataclass(slots=True)
class EvidenceWorkflowExecution:
    terminal_status: str
    result: dict[str, object]


def add_event(
    session: Session,
    job: Job,
    event_type: str,
    detail: dict[str, object] | None = None,
    *,
    commit: bool = True,
) -> None:
    session.add(
        JobEvent(
            job_id=job.id,
            user_id=job.user_id,
            event_type=event_type,
            detail_json=json.dumps(detail or {}, ensure_ascii=False),
        )
    )
    if commit:
        session.commit()


def strongest_evidence(session: Session, *, user_id: int, paper: Paper) -> str:
    _, evidence_level, _, _ = accessible_text(session, user_id=user_id, paper=paper)
    return evidence_level


def validate_job_scope(session: Session, job: Job) -> Paper:
    if job.job_type != WORKFLOW_TYPE:
        raise ValueError("Job is not an evidence workflow")
    payload = json.loads(job.payload_json)
    if not isinstance(payload, dict):
        raise ValueError("Evidence workflow payload must be an object")
    raw_paper_id = payload.get("paper_id")
    if isinstance(raw_paper_id, bool) or not isinstance(raw_paper_id, int):
        raise ValueError("paper_id must be an integer")
    paper = session.get(Paper, raw_paper_id)
    if paper is None:
        raise LookupError("Paper not found")
    if job.project_id is not None:
        owned = session.scalar(
            select(ResearchProject.id).where(
                ResearchProject.id == job.project_id,
                ResearchProject.user_id == job.user_id,
            )
        )
        if owned is None:
            raise LookupError("Project not found")
    return paper


def _cancelled(session: Session, job: Job) -> bool:
    session.refresh(job)
    return job.status == "cancelled" or job.cancelled_at is not None


async def execute_evidence_workflow(
    session: Session,
    *,
    settings: Settings,
    job_id: int,
    search_service: FederatedSearchService,
    oa_resolver: Resolver,
    pdf_fetcher: Fetcher,
    analysis_provider: Any | None = None,
    prompt_version: str = "paper-analysis-v2",
    storage: DurableStorage | None = None,
) -> EvidenceWorkflowExecution:
    """Execute one workflow from its current persisted job.

    External-source failures become an auditable partial result whenever the
    deterministic analysis can still run. A local invariant failure raises so
    the worker's bounded retry contract remains effective.
    """

    job = session.get(Job, job_id)
    if job is None:
        raise LookupError("Evidence workflow not found")
    if job.status == "cancelled":
        return EvidenceWorkflowExecution("cancelled", json.loads(job.result_json))
    paper = validate_job_scope(session, job)
    payload = json.loads(job.payload_json)
    sources = [str(item) for item in payload.get("sources", []) if isinstance(item, str)]
    allow_oa = bool(payload.get("allow_oa_fulltext", True))
    confirm_limited = bool(payload.get("confirm_limited_license", False))

    warnings: list[str] = []
    enrichment_warnings: list[str] = []
    source_status: dict[str, object] = {}
    document_id: int | None = None
    acquisition_run_id: str | None = None
    evidence_before = strongest_evidence(session, user_id=job.user_id, paper=paper)

    add_event(
        session,
        job,
        "identity_resolution",
        {
            "paper_id": paper.id,
            "doi_present": bool(paper.doi),
            "arxiv_id_present": bool(paper.arxiv_id),
            "evidence_before": evidence_before,
        },
    )
    if _cancelled(session, job):
        return EvidenceWorkflowExecution("cancelled", {})

    evidence_after_abstract = evidence_before
    if evidence_before not in FULLTEXT_LEVELS:
        try:
            acquisition = await acquire_paper_evidence(
                session,
                user_id=job.user_id,
                paper_id=paper.id,
                project_id=job.project_id,
                requested_sources=sources,
                search_service=search_service,
            )
            acquisition_run_id = acquisition.run_id
            source_status.update(
                {
                    name: status.model_dump(mode="json")
                    for name, status in acquisition.source_status.items()
                }
            )
            evidence_after_abstract = acquisition.evidence_level_after
            add_event(
                session,
                job,
                "abstract_acquisition",
                {
                    "outcome": acquisition.outcome,
                    "run_id": acquisition.run_id,
                    "queried_sources": acquisition.queried_sources,
                    "source_status": source_status,
                    "evidence_after": evidence_after_abstract,
                },
            )
        except EvidenceAcquisitionError as exc:
            warnings.append(str(exc))
            add_event(
                session,
                job,
                "abstract_acquisition",
                {"outcome": "failed", "error": str(exc)},
            )
    else:
        add_event(
            session,
            job,
            "abstract_acquisition",
            {"outcome": "skipped_existing_fulltext", "evidence_after": evidence_before},
        )

    if _cancelled(session, job):
        return EvidenceWorkflowExecution("cancelled", {})

    resolution = OpenAccessResolution()
    current_paper = session.get(Paper, paper.id)
    if current_paper is None:
        raise LookupError("Paper not found")
    current_evidence = strongest_evidence(session, user_id=job.user_id, paper=current_paper)
    if allow_oa and current_evidence not in FULLTEXT_LEVELS:
        identity = PaperIdentity(
            doi=current_paper.doi,
            arxiv_id=current_paper.arxiv_id,
            title=current_paper.title,
            publication_year=current_paper.publication_year,
        )
        try:
            resolution = await oa_resolver.resolve(identity)
            add_event(
                session,
                job,
                "oa_location_discovery",
                {
                    "source_status": resolution.source_status,
                    "errors": resolution.errors,
                    "candidate_count": len(resolution.candidates),
                },
            )
            add_event(
                session,
                job,
                "license_policy",
                {
                    "candidates": [
                        {
                            "source": candidate.source,
                            "source_record_id": candidate.source_record_id,
                            "license": candidate.normalized_license or candidate.license,
                            "access_decision": candidate.access_decision,
                            "rejection_reason": candidate.rejection_reason,
                        }
                        for candidate in resolution.candidates
                    ],
                    "selected_decision": (
                        resolution.selected.access_decision if resolution.selected else None
                    ),
                },
            )
        except Exception as exc:
            warning = f"OA resolution failed: {type(exc).__name__}: {exc}"
            warnings.append(warning)
            add_event(session, job, "oa_location_discovery", {"error": warning})

        selected = resolution.selected
        permitted = selected is not None and (
            selected.access_decision == "auto_ingest"
            or (
                selected.access_decision == "requires_user_confirmation"
                and confirm_limited
            )
        )
        if permitted and selected is not None:
            try:
                add_event(
                    session,
                    job,
                    "remote_pdf_fetch",
                    {"source": selected.source, "source_record_id": selected.source_record_id},
                )
                fetched = await pdf_fetcher.fetch(selected)
                add_event(
                    session,
                    job,
                    "pdf_security_validation",
                    {
                        "final_url": fetched.final_url,
                        "sha256": fetched.sha256,
                        "size_bytes": fetched.size_bytes,
                        "response_hash": fetched.response_hash,
                    },
                )
                document = ingest_open_access_pdf(
                    session,
                    settings=settings,
                    user_id=job.user_id,
                    paper=current_paper,
                    candidate=selected,
                    fetched=fetched,
                    acquisition_run_id=acquisition_run_id or f"job-{job.id}",
                    user_confirmed_limited_license=confirm_limited,
                    storage=storage,
                )
                session.commit()
                document_id = document.id
                add_event(
                    session,
                    job,
                    "pdf_parse_and_index",
                    {
                        "document_id": document.id,
                        "parse_status": document.parse_status,
                        "evidence_level": document.evidence_level,
                    },
                )
                if document.parse_status != "succeeded":
                    warnings.append("OA PDF contained no extractable text")
            except Exception as exc:
                warning = f"OA PDF acquisition failed: {type(exc).__name__}: {exc}"
                warnings.append(warning)
                add_event(session, job, "remote_pdf_fetch", {"error": warning})
        elif selected is not None:
            warnings.append(
                f"OA candidate not ingested: access_decision={selected.access_decision}"
            )
    else:
        add_event(
            session,
            job,
            "oa_location_discovery",
            {
                "outcome": "skipped",
                "reason": "disabled_or_existing_fulltext",
                "evidence_level": current_evidence,
            },
        )

    if _cancelled(session, job):
        return EvidenceWorkflowExecution("cancelled", {})

    analysis = run_paper_analysis(
        session,
        user_id=job.user_id,
        paper_id=paper.id,
        project_id=job.project_id,
        provider_override=analysis_provider,
        prompt_version=prompt_version,
    )
    add_event(
        session,
        job,
        "deterministic_analysis",
        {"analysis_id": analysis.id, "evidence_level": analysis.evidence_level},
    )
    # Optional LLM/card/map stages are explicit hooks; later services replace
    # these audit-safe skipped events without changing the workflow contract.
    add_event(
        session,
        job,
        "optional_llm_enrichment",
        {
            "outcome": analysis.analysis_mode,
            "provider": analysis.provider,
            "model_name": analysis.model_name,
            "fallback_reason": analysis.fallback_reason,
        },
    )
    refreshed_for_cards = session.get(Paper, paper.id)
    if refreshed_for_cards is None:
        raise LookupError("Paper not found")
    try:
        authors = refresh_author_cards(session, refreshed_for_cards)
        add_event(
            session,
            job,
            "author_card_refresh",
            {"outcome": "succeeded", "count": len(authors)},
        )
    except Exception as exc:
        warning = f"Author card refresh failed: {type(exc).__name__}: {exc}"
        enrichment_warnings.append(warning)
        session.rollback()
        job = session.get(Job, job_id)
        if job is None:
            raise LookupError("Evidence workflow not found") from None
        add_event(session, job, "author_card_refresh", {"outcome": "failed", "error": warning})

    try:
        datasets = refresh_dataset_cards(session, analysis)
        add_event(
            session,
            job,
            "dataset_card_refresh",
            {"outcome": "succeeded", "count": len(datasets)},
        )
    except Exception as exc:
        warning = f"Dataset card refresh failed: {type(exc).__name__}: {exc}"
        enrichment_warnings.append(warning)
        session.rollback()
        job = session.get(Job, job_id)
        if job is None:
            raise LookupError("Evidence workflow not found") from None
        add_event(session, job, "dataset_card_refresh", {"outcome": "failed", "error": warning})

    add_event(session, job, "direction_cluster_refresh", {"outcome": "not_requested"})

    refreshed_paper = session.get(Paper, paper.id)
    if refreshed_paper is None:
        raise LookupError("Paper not found")
    evidence_after = strongest_evidence(session, user_id=job.user_id, paper=refreshed_paper)
    terminal = "succeeded" if evidence_after in FULLTEXT_LEVELS and not warnings else "partial"
    result: dict[str, object] = {
        "paper_id": paper.id,
        "project_id": job.project_id,
        "evidence_before": evidence_before,
        "evidence_after_abstract": evidence_after_abstract,
        "evidence_after": evidence_after,
        "analysis_id": analysis.id,
        "document_id": document_id,
        "acquisition_run_id": acquisition_run_id,
        "source_status": source_status,
        "oa_resolution": resolution.model_dump(mode="json"),
        "warnings": warnings,
        "enrichment_warnings": enrichment_warnings,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    return EvidenceWorkflowExecution(terminal, result)


def finalize_execution(session: Session, job: Job, execution: EvidenceWorkflowExecution) -> None:
    job.result_json = json.dumps(execution.result, ensure_ascii=False)
    job.status = execution.terminal_status
    job.error = None
    job.finished_at = datetime.now(UTC)
    job.locked_by = None
    add_event(session, job, execution.terminal_status, execution.result, commit=False)
    session.commit()
