"""Deterministic, auditable paper recommendations.

This module intentionally uses transparent rules. It does not equate citation
counts with suitability and it never hides fixture provenance.
"""

from __future__ import annotations

import json
import re
from contextlib import suppress
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from research_navigator.models import Paper, Recommendation, ResearchProfile, ResearchProject

_TOKEN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", re.IGNORECASE)
_STOP = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "using",
    "based",
    "style",
    "time",
    "series",
    "research",
    "paper",
    "method",
    "study",
}


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in _TOKEN.findall(value) if token.lower() not in _STOP}


def _paper_tokens(paper: Paper) -> set[str]:
    values = [paper.title, paper.abstract or ""]
    for raw in (paper.keywords_json, paper.concepts_json, paper.fields_of_study_json):
        try:
            values.extend(str(item) for item in json.loads(raw))
        except (TypeError, ValueError):
            continue
    return _tokens(" ".join(values))


def _direction_tokens(profile: ResearchProfile | None, project: ResearchProject | None) -> set[str]:
    values: list[str] = []
    if profile:
        values.extend([profile.broad_direction or "", profile.major or ""])
        with suppress(TypeError, ValueError):
            values.extend(str(item) for item in json.loads(profile.keywords_json))
    if project:
        values.extend([project.name, project.broad_direction or "", project.description or ""])
    return _tokens(" ".join(values))


def _category(paper: Paper, matched: set[str], current_year: int) -> str:
    title = paper.title.lower()
    keywords = " ".join(json.loads(paper.keywords_json)).lower()
    if "survey" in title or "review" in title or "综述" in title:
        return "入门综述"
    if paper.publication_year and paper.publication_year >= current_year - 3 and matched:
        return "高相关近期论文"
    if paper.pdf_url or paper.open_access_status in {"open", "gold", "green", "hybrid"}:
        return "最适合复现"
    if "forecast" in title or "forecast" in keywords:
        return "反向或不同路线论文"
    return "关键方法论文"


def refresh_recommendations(
    session: Session,
    *,
    user_id: int,
    project_id: int | None,
    limit: int,
) -> list[Recommendation]:
    profile = session.scalar(select(ResearchProfile).where(ResearchProfile.user_id == user_id))
    project = None
    if project_id is not None:
        project = session.scalar(
            select(ResearchProject).where(
                ResearchProject.id == project_id, ResearchProject.user_id == user_id
            )
        )
        if project is None:
            raise LookupError("Project not found")
    direction = _direction_tokens(profile, project)
    papers = list(session.scalars(select(Paper).order_by(Paper.publication_year.desc(), Paper.id)))
    ranked: list[tuple[float, Paper, set[str], set[str]]] = []
    for paper in papers:
        terms = _paper_tokens(paper)
        matched = direction & terms
        denominator = max(1, len(direction))
        direction_overlap = len(matched) / denominator
        coverage = len(matched) / max(1, len(terms))
        survey_bonus = 0.12 if "survey" in paper.title.lower() else 0.0
        recency_bonus = 0.08 if paper.publication_year and paper.publication_year >= 2023 else 0.0
        score = min(1.0, 0.72 * direction_overlap + 0.20 * coverage + survey_bonus + recency_bonus)
        ranked.append((round(score, 6), paper, matched, terms))
    ranked.sort(key=lambda item: (item[0], item[1].publication_year or 0), reverse=True)

    session.execute(
        delete(Recommendation).where(
            Recommendation.user_id == user_id,
            Recommendation.project_id == project_id,
        )
    )
    output: list[Recommendation] = []
    now_year = datetime.now(UTC).year
    for score, paper, matched, _ in ranked[:limit]:
        category = _category(paper, matched, now_year)
        matched_sorted = sorted(matched)
        if matched_sorted:
            reason = f"与研究档案共享术语：{', '.join(matched_sorted[:8])}。"
        else:
            reason = "当前本地论文库中直接匹配证据较弱，作为补充路线保留。"
        evidence = {
            "rule_version": "recommendation-v1",
            "matched_terms": matched_sorted,
            "direction_term_count": len(direction),
            "is_fixture_sensitive": True,
            "warning": "fixture 记录仅用于演示，不可作为真实科研证据。",
        }
        row = Recommendation(
            user_id=user_id,
            project_id=project_id,
            paper_id=paper.id,
            category=category,
            score=score,
            reason=reason,
            evidence_json=json.dumps(evidence, ensure_ascii=False),
            recommendation_version="recommendation-v1",
        )
        session.add(row)
        output.append(row)
    session.commit()
    for row in output:
        session.refresh(row)
    return output
