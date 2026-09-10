"""Persisted evidence guard shared by HTTP and worker entrypoints."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.gaps.eligibility import VERSION, evaluate_evidence, fingerprint
from research_navigator.gaps.matrix import build_evidence_matrix
from research_navigator.models import (
    GapCandidate,
    PaperSet,
    PaperSetItem,
    ResearchProfile,
    ResearchProject,
)


class StaleGapEvidence(ValueError):
    def __init__(self) -> None:
        super().__init__(
            "当前方向、选文或原文证据尚未通过核验，请重新比较材料后生成候选。旧记录仅供回顾。"
        )


def challenge_fingerprint(row: GapCandidate) -> str:
    """Bind review to persisted search evidence, without timestamp/ORM formatting."""
    coverage = json.loads(row.coverage_json)
    return fingerprint(
        {
            "queries": json.loads(row.challenge_queries_json),
            "counter_evidence": json.loads(row.counter_evidence_json),
            "sources": json.loads(row.data_sources_json),
            "source_failures": coverage.get("challenge_source_failures"),
            "complete": row.challenge_completed_at is not None,
        }
    )


def context_fingerprint(session: Session, project: ResearchProject, paper_ids: list[int]) -> str:
    profile = session.scalar(
        select(ResearchProfile).where(ResearchProfile.user_id == project.user_id)
    )
    return fingerprint(
        {
            "version": VERSION,
            "user_id": project.user_id,
            "project_id": project.id,
            "name": project.name,
            "direction": project.broad_direction,
            "description": project.description,
            "profile": None
            if profile is None
            else {
                "direction": profile.broad_direction,
                "keywords": profile.keywords_json,
                "excluded": profile.excluded_terms_json,
                "preferences": profile.preferences_json,
                "constraints": profile.compute_constraints,
            },
            "paper_ids": paper_ids,
            "matrix": build_evidence_matrix(
                session, user_id=project.user_id, project_id=project.id, paper_ids=paper_ids
            ),
        }
    )


def assert_current_gap(session: Session, row: GapCandidate) -> None:
    project = session.get(ResearchProject, row.project_id)
    paper_set = session.get(PaperSet, row.paper_set_id) if row.paper_set_id else None
    if (
        project is None
        or project.user_id != row.user_id
        or paper_set is None
        or paper_set.user_id != row.user_id
        or paper_set.project_id not in (None, project.id)
    ):
        raise StaleGapEvidence()
    ids = list(
        session.scalars(
            select(PaperSetItem.paper_id)
            .where(PaperSetItem.paper_set_id == paper_set.id)
            .order_by(PaperSetItem.position, PaperSetItem.id)
        )
    )
    coverage = json.loads(row.coverage_json)
    matrix = build_evidence_matrix(
        session, user_id=row.user_id, project_id=project.id, paper_ids=ids
    )
    gate = evaluate_evidence(project.broad_direction or project.name, matrix)
    if (
        not gate.allowed
        or coverage.get("eligibility", {}).get("version") != VERSION
        or coverage.get("context_fingerprint") != context_fingerprint(session, project, ids)
    ):
        raise StaleGapEvidence()
    if row.challenge_completed_at is not None and coverage.get(
        "challenge_fingerprint"
    ) != challenge_fingerprint(row):
        raise StaleGapEvidence()
