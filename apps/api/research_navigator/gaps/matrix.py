"""Build an auditable research evidence matrix from persisted papers and analyses."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.analysis.structured import PaperAnalysisOutput
from research_navigator.models import Paper, PaperAnalysisRecord


def build_evidence_matrix(
    session: Session, *, user_id: int, paper_ids: list[int]
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
        matrix.append(
            {
                "paper_id": paper.id,
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
