"""Reusable evidence-bounded paper analysis service."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from research_navigator.analysis.llm_validation import validate_and_merge_llm_analysis
from research_navigator.analysis.matching import assess_direction_match
from research_navigator.analysis.reproduction import assess_reproduction
from research_navigator.analysis.structured import (
    CitationLocator,
    EvidenceSpan,
    analyze_accessible_text,
)
from research_navigator.models import (
    AgentRun,
    Paper,
    PaperAnalysisRecord,
    PaperChunk,
    PaperDocument,
    PaperSource,
    ResearchProfile,
    ResearchProject,
    ToolCall,
)


def accessible_text(
    session: Session, *, user_id: int, paper: Paper
) -> tuple[str, str, list[CitationLocator], list[EvidenceSpan]]:
    document = session.scalar(
        select(PaperDocument)
        .where(
            PaperDocument.paper_id == paper.id,
            PaperDocument.parse_status == "succeeded",
            or_(PaperDocument.user_id == user_id, PaperDocument.user_id.is_(None)),
        )
        .order_by(PaperDocument.created_at.desc(), PaperDocument.id.desc())
    )
    if document is not None:
        chunks = list(
            session.scalars(
                select(PaperChunk)
                .where(PaperChunk.document_id == document.id)
                .order_by(PaperChunk.chunk_index)
            )
        )
        spans = [
            EvidenceSpan(
                text=chunk.text,
                citation=CitationLocator(
                    source_type=chunk.source_type,
                    section=chunk.section,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    chunk_id=chunk.id,
                ),
            )
            for chunk in chunks
        ]
        return (
            "\n".join(chunk.text for chunk in chunks),
            document.evidence_level,
            [span.citation for span in spans],
            spans,
        )
    abstract_is_verified = session.scalar(
        select(PaperSource.id).where(
            PaperSource.paper_id == paper.id,
            PaperSource.provides_abstract.is_(True),
            PaperSource.is_fixture.is_(False),
        )
    ) is not None
    if paper.abstract and abstract_is_verified:
        citation = CitationLocator(
            source_type="abstract",
            section="Abstract",
            page_start=None,
            page_end=None,
            chunk_id=None,
        )
        return (
            paper.abstract,
            "abstract_only",
            [citation],
            [EvidenceSpan(text=paper.abstract, citation=citation)],
        )
    citation = CitationLocator(
        source_type="metadata",
        section="Metadata",
        page_start=None,
        page_end=None,
        chunk_id=None,
    )
    return (
        paper.title,
        "metadata_only",
        [citation],
        [EvidenceSpan(text=paper.title, citation=citation)],
    )


def _stable_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def run_paper_analysis(
    session: Session,
    *,
    user_id: int,
    paper_id: int,
    project_id: int | None = None,
    commit: bool = True,
    provider_override: Any | None = None,
    prompt_version: str = "paper-analysis-v2",
) -> PaperAnalysisRecord:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise LookupError("Paper not found")
    if project_id is not None:
        project = session.scalar(
            select(ResearchProject).where(
                ResearchProject.id == project_id,
                ResearchProject.user_id == user_id,
            )
        )
        if project is None:
            raise LookupError("Project not found")
    profile = session.scalar(select(ResearchProfile).where(ResearchProfile.user_id == user_id))
    text, evidence_level, citations, evidence_spans = accessible_text(
        session, user_id=user_id, paper=paper
    )
    deterministic = analyze_accessible_text(
        paper_id=paper.id,
        text=text,
        evidence_level=evidence_level,  # type: ignore[arg-type]
        citations=citations,
        evidence_spans=evidence_spans,
    )
    analysis = deterministic
    input_contract = [
        {
            "chunk_id": span.citation.chunk_id,
            "text_hash": hashlib.sha256(span.text.encode("utf-8")).hexdigest(),
            "text_length": len(span.text),
            "citation": span.citation.model_dump(mode="json"),
        }
        for span in evidence_spans
    ]
    provider_name = "deterministic"
    model_name: str | None = None
    analysis_mode = "deterministic"
    fallback_reason: str | None = None
    analysis_run_id: str | None = None
    provider_output_hash: str | None = None
    input_evidence_hash = _stable_hash(input_contract)

    if provider_override is not None:
        analysis_run_id = uuid.uuid4().hex
        provider_name = str(getattr(provider_override, "provider_name", type(provider_override).__name__))
        model_name = getattr(provider_override, "model_name", None)
        run = AgentRun(
            run_id=analysis_run_id,
            user_id=user_id,
            project_id=project_id,
            workflow_type="paper_analysis",
            workflow_version="paper-analysis-hybrid-v1",
            prompt_version=prompt_version,
            model_provider=provider_name,
            model_name=model_name,
            status="running",
            input_json=json.dumps(
                {
                    "paper_id": paper.id,
                    "evidence_level": evidence_level,
                    "input_evidence_hash": input_evidence_hash,
                    "chunks": input_contract,
                },
                ensure_ascii=False,
            ),
        )
        session.add(run)
        session.flush()
        snippets = [
            {
                "chunk_id": span.citation.chunk_id,
                "text": span.text,
                "citation": span.citation.model_dump(mode="json"),
            }
            for span in evidence_spans
        ]
        started = time.perf_counter()
        tool = ToolCall(
            run_id=analysis_run_id,
            user_id=user_id,
            tool_name="analysis_provider.complete",
            input_json=json.dumps(
                {
                    "paper_id": paper.id,
                    "evidence_level": evidence_level,
                    "input_evidence_hash": input_evidence_hash,
                    "chunk_ids": [item["chunk_id"] for item in snippets],
                },
                ensure_ascii=False,
            ),
            output_json="{}",
            status="running",
            attempt_count=1,
        )
        session.add(tool)
        session.flush()
        try:
            raw_output = provider_override.complete(snippets=snippets)
            provider_output_hash = _stable_hash(raw_output)
            analysis = validate_and_merge_llm_analysis(
                deterministic,
                raw_output,
                accessible_snippets=snippets,
                evidence_level=evidence_level,  # type: ignore[arg-type]
            )
            analysis_mode = "hybrid"
            tool.status = "succeeded"
            tool.response_status = "validated"
            tool.validated_output_hash = provider_output_hash
            tool.output_json = json.dumps(
                {
                    "provider_output_hash": provider_output_hash,
                    "merged_fields": sorted(
                        field
                        for field in analysis.field_states
                        if analysis.field_states.get(field) == "evidenced"
                        and deterministic.field_states.get(field) != "evidenced"
                    ),
                },
                ensure_ascii=False,
            )
            run.status = "succeeded"
            run.output_json = json.dumps(
                {"analysis_mode": analysis_mode, "provider_output_hash": provider_output_hash},
                ensure_ascii=False,
            )
        except Exception as exc:
            fallback_reason = f"{type(exc).__name__}: {exc}"
            analysis_mode = "deterministic_fallback"
            tool.status = "failed"
            tool.response_status = "rejected_or_unavailable"
            tool.error = fallback_reason
            tool.output_json = json.dumps({"fallback": True}, ensure_ascii=False)
            run.status = "succeeded_with_fallback"
            run.error = fallback_reason
            run.output_json = json.dumps(
                {"analysis_mode": analysis_mode, "fallback_reason": fallback_reason},
                ensure_ascii=False,
            )
        finally:
            finished = datetime.now(UTC)
            tool.finished_at = finished
            tool.latency_ms = int((time.perf_counter() - started) * 1000)
            run.finished_at = finished
            run.output_hash = _stable_hash(json.loads(run.output_json))

    direction = assess_direction_match(profile, paper, analysis)
    reproduction = assess_reproduction(paper, analysis)
    row = PaperAnalysisRecord(
        user_id=user_id,
        paper_id=paper.id,
        project_id=project_id,
        evidence_level=analysis.evidence_level,
        analysis_version=analysis.analysis_version,
        analysis_json=analysis.model_dump_json(),
        direction_similarity_json=direction.model_dump_json(),
        reproduction_assessment_json=reproduction.model_dump_json(),
        analysis_run_id=analysis_run_id,
        analysis_mode=analysis_mode,
        provider=provider_name,
        model_name=model_name,
        prompt_version=prompt_version if provider_override is not None else None,
        input_evidence_hash=input_evidence_hash,
        provider_output_hash=provider_output_hash,
        fallback_reason=fallback_reason,
    )
    session.add(row)
    if commit:
        session.commit()
        session.refresh(row)
    else:
        session.flush()
    return row
