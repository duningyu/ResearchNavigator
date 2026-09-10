"""Build an auditable research evidence matrix from persisted papers and analyses."""

from __future__ import annotations

import json
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from research_navigator.analysis.structured import PaperAnalysisOutput
from research_navigator.documents.material_binding import (
    expected_arxiv_identity,
    material_is_current,
)
from research_navigator.gaps.eligibility import fingerprint
from research_navigator.models import Paper, PaperAnalysisRecord, PaperChunk, PaperDocument


def build_evidence_matrix(
    session: Session, *, user_id: int, paper_ids: list[int], project_id: int | None = None
) -> list[dict[str, object]]:
    matrix: list[dict[str, object]] = []
    for paper_id in paper_ids:
        paper = session.get(Paper, paper_id)
        if paper is None:
            continue
        analysis_row = session.scalar(
            select(PaperAnalysisRecord)
            .where(
                PaperAnalysisRecord.user_id == user_id,
                PaperAnalysisRecord.paper_id == paper_id,
                *([PaperAnalysisRecord.project_id == project_id] if project_id is not None else []),
            )
            .order_by(PaperAnalysisRecord.created_at.desc(), PaperAnalysisRecord.id.desc())
        )
        analysis = (
            PaperAnalysisOutput.model_validate_json(analysis_row.analysis_json)
            if analysis_row is not None
            else None
        )
        keywords = json.loads(paper.keywords_json)
        text = " ".join([paper.title, paper.abstract or "", " ".join(keywords)]).lower()
        task = "unknown"
        if "risk ranking" in text or "alert ranking" in text:
            task = "risk ranking"
        elif "anomaly prediction" in text or "failure prediction" in text:
            task = "anomaly/failure prediction"
        elif "anomaly detection" in text:
            task = "anomaly detection"
        elif "forecast" in text:
            task = "forecasting"
        field_states = analysis.field_states if analysis else {}
        field_citations = (
            {
                key: [citation.model_dump(mode="json") for citation in value]
                for key, value in analysis.field_citations.items()
            }
            if analysis
            else {}
        )
        document = session.scalar(
            select(PaperDocument).where(
                PaperDocument.paper_id == paper_id,
                or_(PaperDocument.user_id == user_id, PaperDocument.user_id.is_(None)),
            ).order_by(PaperDocument.created_at.desc(), PaperDocument.id.desc())
        )
        current_material = document is not None and material_is_current(
        document.material_binding_json, paper_id=paper.id, arxiv_id=expected_arxiv_identity(paper),
            doi=paper.doi, sha256=document.sha256,
        ) and document.parse_status in {"succeeded", "partial"}
        chunks = list(
            session.scalars(
                select(PaperChunk)
                .join(PaperDocument, PaperDocument.id == PaperChunk.document_id)
                .where(
                    PaperChunk.paper_id == paper_id,
                    PaperChunk.user_id == user_id,
                    PaperDocument.paper_id == paper_id,
                    PaperDocument.user_id == user_id,
                    PaperDocument.id == (document.id if current_material and document else -1),
                )
            )
        )
        for citations in field_citations.values():
            for citation in citations:
                support = " ".join(str(citation.get("supporting_text") or "").casefold().split())
                material = paper.abstract or "" if citation.get("source_type") == "abstract" else ""
                if citation.get("chunk_id") is not None:
                    chunk = next((c for c in chunks if c.id == citation["chunk_id"]), None)
                    material = chunk.text if chunk is not None else ""
                citation["material_verified"] = bool(support) and support in " ".join(
                    material.casefold().split()
                )
        matrix.append(
            {
                "paper_id": paper.id,
                "work_identity": (
                    "arxiv:" + re.sub(r"v\d+$", "", paper.arxiv_id.casefold())
                    if paper.arxiv_id
                    else "doi:" + paper.doi.casefold().removeprefix("https://doi.org/")
                    if paper.doi
                    else "title:" + " ".join(paper.title.casefold().split())
                ),
                "material_fingerprint": fingerprint(
                    {
                        "title": paper.title,
                        "abstract": paper.abstract,
                        "doi": paper.doi,
                        "arxiv_id": paper.arxiv_id,
                        "analysis": analysis_row.analysis_json if analysis_row else None,
                        "analysis_id": analysis_row.id if analysis_row else None,
                        "current_material": (
                            [document.id, document.sha256, document.material_binding_json,
                             document.parse_status, document.ingestion_version]
                            if document else None
                        ),
                        "chunks": [(c.id, c.text_hash, fingerprint(c.text)) for c in chunks],
                    }
                ),
                "title": paper.title,
                "publication_year": paper.publication_year,
                "venue": paper.venue,
                "task": task,
                "research_problem": analysis.research_problem if analysis else None,
                "input": analysis.task_definition.input if analysis else None,
                "output": analysis.task_definition.output if analysis else None,
                "data_type": "multivariate time series"
                if "multivariate" in text
                else "time series"
                if "time series" in text
                else None,
                "datasets": analysis.datasets if analysis else [],
                "baselines": analysis.baselines if analysis else [],
                "metrics": analysis.metrics if analysis else [],
                "experimental_protocol": analysis.experimental_protocol if analysis else [],
                "supervision": None,
                "prediction_horizon": "future window"
                if any(
                    term in text for term in ("future horizon", "future-window", "future window")
                )
                else None,
                "methods": analysis.core_methods if analysis else [],
                "method_innovation": analysis.method_innovation if analysis else [],
                "theoretical_contribution": analysis.theoretical_contribution if analysis else [],
                "research_route": analysis.research_route if analysis else [],
                "business_constraints": [
                    term
                    for term in ("fixed alert budget", "high false positive", "online")
                    if term in text
                ],
                "handles_imbalance": "class imbalance" in text,
                "evaluates_false_alarms": any(
                    term in text for term in ("false alarm", "false positive", "precision")
                ),
                "event_level_metrics": "event" in text,
                "code_verified": False,
                "data_verified": False,
                "future_work_explicit": analysis.future_work_explicit if analysis else [],
                "limitations_author_stated": analysis.limitations_author_stated if analysis else [],
                "limitations_inferred": analysis.limitations_inferred if analysis else [],
                "major_results": analysis.major_results if analysis else [],
                "claimed_contributions": analysis.claimed_contributions if analysis else [],
                "evidence_level": analysis.evidence_level if analysis else "metadata_only",
                "field_states": field_states,
                "field_citations": field_citations,
                "missing_fields": analysis.missing_fields
                if analysis
                else [
                    "research_problem",
                    "core_methods",
                    "datasets",
                    "experimental_protocol",
                    "future_work_explicit",
                    "limitations_author_stated",
                ],
            }
        )
    return matrix
