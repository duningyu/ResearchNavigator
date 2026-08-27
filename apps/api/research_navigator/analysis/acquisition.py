"""Bounded, auditable acquisition of stronger paper metadata evidence."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.analysis.service import accessible_text, run_paper_analysis
from research_navigator.analysis.structured import EvidenceLevel
from research_navigator.models import (
    AgentRun,
    Paper,
    PaperSource,
    ResearchProject,
    SourceRequest,
    ToolCall,
)
from research_navigator.scholarly.base import PaperRecord, SearchRequest, SourceStatus
from research_navigator.scholarly.normalize import (
    normalize_arxiv_id,
    normalize_doi,
    normalize_title,
)
from research_navigator.scholarly.repository import upsert_paper
from research_navigator.scholarly.service import FederatedSearchService

WORKFLOW_VERSION = "evidence-acquisition-v2"
Outcome = Literal[
    "abstract_acquired",
    "no_matching_evidence",
    "no_eligible_source",
    "source_unavailable",
    "already_sufficient",
]
QueryKind = Literal["doi", "arxiv", "title_year"]
FULLTEXT_LEVELS = {
    "open_fulltext",
    "user_uploaded_fulltext",
    "publisher_authorized_fulltext",
}


class EvidenceAcquisitionError(RuntimeError):
    """The audited acquisition run failed after it was created."""


@dataclass(slots=True)
class EvidenceAcquisitionResult:
    run_id: str
    outcome: Outcome
    evidence_level_before: EvidenceLevel
    evidence_level_after: EvidenceLevel
    queried_sources: list[str]
    source_status: dict[str, SourceStatus]
    paper: Paper
    analysis_id: int


def _query_stages(paper: Paper) -> list[tuple[QueryKind, str]]:
    stages: list[tuple[QueryKind, str]] = []
    if paper.doi:
        stages.append(("doi", paper.doi))
    if paper.arxiv_id:
        stages.append(("arxiv", paper.arxiv_id))
    if paper.publication_year is not None:
        stages.append(("title_year", paper.title))
    return stages


def _matches_target(paper: Paper, record: PaperRecord, query_kind: QueryKind) -> bool:
    if paper.doi and record.doi and normalize_doi(record.doi) != normalize_doi(paper.doi):
        return False
    if (
        paper.arxiv_id
        and record.arxiv_id
        and normalize_arxiv_id(record.arxiv_id) != normalize_arxiv_id(paper.arxiv_id)
    ):
        return False
    if query_kind == "doi":
        return normalize_doi(record.doi) == normalize_doi(paper.doi)
    if query_kind == "arxiv":
        return normalize_arxiv_id(record.arxiv_id) == normalize_arxiv_id(paper.arxiv_id)
    return bool(
        paper.publication_year is not None
        and record.publication_year == paper.publication_year
        and normalize_title(record.title) == paper.normalized_title
    )


def _real_abstract_record(
    paper: Paper, records: list[PaperRecord], query_kind: QueryKind
) -> PaperRecord | None:
    candidates = [
        record
        for record in records
        if record.abstract
        and _matches_target(paper, record, query_kind)
        and record.abstract_provenance is not None
        and not record.abstract_provenance.is_fixture
    ]
    return max(candidates, key=lambda item: len(item.abstract or ""), default=None)


def _has_verified_abstract(session: Session, paper_id: int) -> bool:
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


def _record_source_requests(
    session: Session,
    *,
    run_id: str,
    user_id: int,
    project_id: int | None,
    request_payload: SearchRequest,
    statuses: dict[str, SourceStatus],
    records: list[PaperRecord],
    started_at: datetime,
    finished_at: datetime,
) -> None:
    for source, status in statuses.items():
        source_records = [
            {
                "source_id": provenance.source_id,
                "source_url": provenance.source_url,
                "raw_hash": provenance.raw_hash,
                "fetched_at": provenance.fetched_at.isoformat(),
                "is_fixture": provenance.is_fixture,
            }
            for record in records
            for provenance in record.source_provenance
            if provenance.source == source
        ]
        raw_hashes = json.dumps(
            [item["raw_hash"] for item in source_records],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        metadata = status.model_dump(mode="json")
        metadata["raw_response_hash"] = hashlib.sha256(raw_hashes).hexdigest()
        metadata["audit_semantics"] = (
            "aggregate hash of persisted per-record raw hashes; not a byte-for-byte HTTP body hash"
        )
        session.add(
            SourceRequest(
                run_id=run_id,
                user_id=user_id,
                project_id=project_id,
                source=source,
                query=request_payload.query,
                request_json=json.dumps(
                    request_payload.model_dump(mode="json"), ensure_ascii=False
                ),
                response_metadata_json=json.dumps(metadata, ensure_ascii=False),
                source_records_json=json.dumps(source_records, ensure_ascii=False),
                status=status.status,
                error=(
                    status.detail
                    if status.status not in {"ok", "disabled", "not_configured"}
                    else None
                ),
                started_at=started_at,
                finished_at=finished_at,
            )
        )


def _finish_failed_run(session: Session, run_id: str, exc: Exception) -> None:
    session.rollback()
    run = session.scalar(select(AgentRun).where(AgentRun.run_id == run_id))
    if run is None:
        return
    error = f"{type(exc).__name__}: {exc}"
    run.status = "failed"
    run.error = error
    run.output_json = json.dumps({"outcome": "failed"}, ensure_ascii=False)
    run.finished_at = datetime.now(UTC)
    session.add(
        ToolCall(
            run_id=run_id,
            user_id=run.user_id,
            tool_name="evidence_acquisition.workflow",
            input_json="{}",
            output_json="{}",
            status="failed",
            error=error,
            finished_at=run.finished_at,
        )
    )
    session.commit()


async def acquire_paper_evidence(
    session: Session,
    *,
    user_id: int,
    paper_id: int,
    project_id: int | None,
    requested_sources: list[str],
    search_service: FederatedSearchService,
) -> EvidenceAcquisitionResult:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise LookupError("Paper not found")
    if project_id is not None:
        owned_project = session.scalar(
            select(ResearchProject.id).where(
                ResearchProject.id == project_id,
                ResearchProject.user_id == user_id,
            )
        )
        if owned_project is None:
            raise LookupError("Project not found")

    _, raw_evidence_before, _, _ = accessible_text(session, user_id=user_id, paper=paper)
    evidence_before: EvidenceLevel = raw_evidence_before  # type: ignore[assignment]
    run_id = uuid.uuid4().hex
    run = AgentRun(
        run_id=run_id,
        user_id=user_id,
        project_id=project_id,
        workflow_type="evidence_acquisition",
        workflow_version=WORKFLOW_VERSION,
        status="running",
        input_json=json.dumps(
            {"paper_id": paper_id, "requested_sources": requested_sources},
            ensure_ascii=False,
        ),
    )
    session.add(run)
    session.commit()

    try:
        paper = session.get(Paper, paper_id)
        if paper is None:
            raise LookupError("Paper not found")
        eligible_sources = [
            name
            for name, adapter in search_service.adapters.items()
            if adapter.supports_evidence_acquisition
        ]
        queried_sources = list(
            dict.fromkeys(
                name
                for name in (requested_sources or eligible_sources)
                if name in eligible_sources
            )
        )
        source_status: dict[str, SourceStatus] = {}
        outcome: Outcome = "already_sufficient"
        verified_abstract = _has_verified_abstract(session, paper.id)

        if evidence_before not in FULLTEXT_LEVELS and not verified_abstract:
            stages = _query_stages(paper)
            if not queried_sources or not stages:
                outcome = "no_eligible_source"
            else:
                outcome = "no_matching_evidence"
                for query_kind, query in stages:
                    request_payload = SearchRequest(
                        query=query, limit=10, sources=queried_sources
                    )
                    started = datetime.now(UTC)
                    result = await search_service.search(request_payload)
                    finished = datetime.now(UTC)
                    source_status.update(result.source_status)
                    matched = _real_abstract_record(paper, result.papers, query_kind)
                    tool_output = {
                        "query_kind": query_kind,
                        "source_status": {
                            name: status.model_dump(mode="json")
                            for name, status in result.source_status.items()
                        },
                        "record_count": len(result.papers),
                        "matched": matched is not None,
                    }
                    session.add(
                        ToolCall(
                            run_id=run_id,
                            user_id=user_id,
                            tool_name="scholarly_search.search_papers",
                            input_json=json.dumps(
                                request_payload.model_dump(mode="json"), ensure_ascii=False
                            ),
                            output_json=json.dumps(tool_output, ensure_ascii=False),
                            status="succeeded",
                            started_at=started,
                            finished_at=finished,
                        )
                    )
                    _record_source_requests(
                        session,
                        run_id=run_id,
                        user_id=user_id,
                        project_id=project_id,
                        request_payload=request_payload,
                        statuses=result.source_status,
                        records=result.papers,
                        started_at=started,
                        finished_at=finished,
                    )
                    if matched is not None:
                        paper = upsert_paper(session, matched)
                        outcome = "abstract_acquired"
                        break
                if outcome == "no_matching_evidence" and source_status and not any(
                    status.status == "ok" for status in source_status.values()
                ):
                    outcome = "source_unavailable"

        analysis = run_paper_analysis(
            session,
            user_id=user_id,
            paper_id=paper_id,
            project_id=project_id,
            commit=False,
        )
        session.flush()
        _, raw_evidence_after, _, _ = accessible_text(
            session, user_id=user_id, paper=paper
        )
        evidence_after: EvidenceLevel = raw_evidence_after  # type: ignore[assignment]
        output = {
            "outcome": outcome,
            "evidence_level_before": evidence_before,
            "evidence_level_after": evidence_after,
            "queried_sources": queried_sources,
        }
        run.status = "succeeded"
        run.output_json = json.dumps(output, ensure_ascii=False)
        run.output_hash = hashlib.sha256(run.output_json.encode("utf-8")).hexdigest()
        run.finished_at = datetime.now(UTC)
        session.commit()
        session.refresh(paper)
        return EvidenceAcquisitionResult(
            run_id=run_id,
            outcome=outcome,
            evidence_level_before=evidence_before,
            evidence_level_after=evidence_after,
            queried_sources=queried_sources,
            source_status=source_status,
            paper=paper,
            analysis_id=analysis.id,
        )
    except Exception as exc:
        _finish_failed_run(session, run_id, exc)
        raise EvidenceAcquisitionError("Evidence acquisition failed") from exc
