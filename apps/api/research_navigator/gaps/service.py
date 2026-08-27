"""Reusable challenge-search service for API and persistent worker."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.gaps.candidate import build_gap_explanation, generate_challenge_queries
from research_navigator.models import AgentRun, GapCandidate, GapEvidence, GapExplanation
from research_navigator.scholarly.base import SearchRequest
from research_navigator.scholarly.repository import upsert_paper
from research_navigator.scholarly.service import FederatedSearchService


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def append_gap_explanation(session: Session, *, row: GapCandidate) -> GapExplanation:
    latest_version = session.scalar(
        select(GapExplanation.version)
        .where(GapExplanation.gap_id == row.id, GapExplanation.user_id == row.user_id)
        .order_by(GapExplanation.version.desc())
    ) or 0
    payload = build_gap_explanation(
        version=int(latest_version) + 1,
        claim=row.claim,
        evidence_matrix=json.loads(row.evidence_matrix_json),
        supporting_evidence=json.loads(row.supporting_evidence_json),
        counter_evidence=json.loads(row.counter_evidence_json),
        direction_snapshot=json.loads(row.direction_snapshot_json),
        risk_factors=json.loads(row.risk_factors_json),
        challenge_queries=json.loads(row.challenge_queries_json),
        minimal_validation=json.loads(row.minimal_validation_json),
        confidence=row.confidence,
    )
    evidence_base = payload.model_dump(mode="json", exclude={"evidence_hash"})
    evidence_hash = hashlib.sha256(_json(evidence_base).encode()).hexdigest()
    payload.evidence_hash = evidence_hash
    explanation = GapExplanation(
        gap_id=row.id,
        user_id=row.user_id,
        version=payload.version,
        provider=payload.provider,
        explanation_json=payload.model_dump_json(),
        evidence_hash=evidence_hash,
        validated=True,
    )
    session.add(explanation)
    session.flush()
    return explanation


async def run_gap_challenge(
    session: Session,
    *,
    user_id: int,
    gap_id: int,
    additional_terms: list[str],
    search_service: FederatedSearchService,
) -> GapCandidate:
    row = session.scalar(
        select(GapCandidate).where(GapCandidate.id == gap_id, GapCandidate.user_id == user_id)
    )
    if row is None:
        raise LookupError("Gap candidate not found")
    queries = generate_challenge_queries(row.scope)
    queries.extend(term.strip() for term in additional_terms if term.strip())
    queries = list(dict.fromkeys(queries))
    counter: list[dict[str, object]] = []
    source_names: set[str] = set()

    for query in queries[:3]:
        result = await search_service.search(SearchRequest(query=query, limit=3))
        for source_name, source_status in result.source_status.items():
            source_names.add(source_name)
            if source_status.status not in {"ok", "disabled", "not_configured"}:
                counter.append(
                    {
                        "query": query,
                        "source": source_name,
                        "status": source_status.status,
                        "detail": source_status.detail,
                    }
                )
        for record in result.papers:
            paper = upsert_paper(session, record)
            counter.append(
                {
                    "paper_id": paper.id,
                    "title": paper.title,
                    "query": query,
                    "is_fixture": any(item.is_fixture for item in record.source_provenance),
                    "relationship": "potential_counter_or_adjacent_evidence",
                }
            )
            session.add(
                GapEvidence(
                    gap_id=row.id,
                    paper_id=paper.id,
                    evidence_role="counter_candidate",
                    rationale=(
                        "Retrieved by challenge query; human relevance review is still required."
                    ),
                    source_query=query,
                )
            )
    row.challenge_queries_json = _json(queries)
    row.counter_evidence_json = _json(counter)
    row.data_sources_json = _json(sorted(source_names))
    row.challenge_completed_at = datetime.now(UTC)
    row.status = "pending_confirmation"
    row.confidence = "medium" if len(counter) >= 2 else "low"
    append_gap_explanation(session, row=row)
    session.add(
        AgentRun(
            run_id=uuid.uuid4().hex,
            user_id=user_id,
            project_id=row.project_id,
            workflow_type="gap_challenge_search",
            workflow_version="gap-workflow-v1",
            prompt_version="challenge-query-v1",
            status="succeeded",
            input_json=_json({"gap_id": row.id, "queries": queries}),
            output_json=_json(counter),
            finished_at=datetime.now(UTC),
            output_hash=hashlib.sha256(_json(counter).encode()).hexdigest(),
        )
    )
    session.commit()
    session.refresh(row)
    return row
