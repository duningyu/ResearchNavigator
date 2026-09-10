"""Deterministic, auditable paper recommendations.

This module intentionally uses transparent rules. It does not equate citation
counts with suitability and it never hides fixture provenance.
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import suppress
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from research_navigator.models import (
    Paper,
    PaperDocument,
    PaperSource,
    Recommendation,
    ResearchProfile,
    ResearchProject,
)

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
    "deep",
    "learning",
    "model",
    "data",
    "algorithm",
    "network",
    "analysis",
    "detection",
    "prediction",
    "future",
    "window",
    "industrial",
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


def _identity(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]


def _profile_identity(profile: ResearchProfile | None, project: ResearchProject | None) -> str:
    payload = {
        "profile": {
            "stage": profile.stage if profile else None,
            "major": profile.major if profile else None,
            "broad_direction": profile.broad_direction if profile else None,
            "keywords": profile.keywords_json if profile else "[]",
            "excluded_terms": profile.excluded_terms_json if profile else "[]",
            "preferences": profile.preferences_json if profile else "[]",
        },
        "project": {
            "id": project.id if project else None,
            "name": project.name if project else None,
            "broad_direction": project.broad_direction if project else None,
            "description": project.description if project else None,
        },
    }
    return f"profile:{_identity(json.dumps(payload, ensure_ascii=False, sort_keys=True))}"


def _paper_identity(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"arxiv:{paper.arxiv_id}"
    if paper.doi:
        return f"doi:{paper.doi}"
    return f"paper:{paper.id}:{_identity(paper.normalized_title)}"


def _material_identity(material: object | None, paper: Paper) -> tuple[str, str]:
    if isinstance(material, PaperDocument):
        return (
            f"document:{material.id}:{material.sha256}",
            "full_text" if "fulltext" in material.evidence_level else "metadata",
        )
    if isinstance(material, PaperSource):
        return (
            f"source:{material.id}:{material.raw_hash or material.source_id}",
            "abstract" if material.provides_abstract and paper.abstract else "metadata",
        )
    if paper.abstract:
        return f"abstract:{hashlib.sha256(paper.abstract.encode('utf-8')).hexdigest()}", "abstract"
    return f"metadata:{paper.id}", "metadata"


def build_reading_recommendation(
    *,
    paper: Paper,
    profile: ResearchProfile | None,
    project: ResearchProject | None,
    material: object | None,
) -> dict[str, object]:
    """Build a material- and profile-bound recommendation, not a score label."""
    paper_identity = _paper_identity(paper)
    material_identity, evidence_level = _material_identity(material, paper)
    profile_identity = _profile_identity(profile, project)
    direction = _direction_tokens(profile, project)
    matched = direction & _paper_tokens(paper)
    task_match = (
        "unknown"
        if not direction or not paper.abstract
        else ("matched" if matched else "mismatched")
    )
    method_terms = {"attention", "transformer", "cnn", "lstm", "neural", "deep"}

    if task_match == "unknown" or evidence_level == "metadata":
        verdict = "insufficient_evidence"
        rationale = "当前材料不足以判断论文与研究任务的适配关系。"
        applicability = "暂不能形成可靠的阅读优先级判断。"
        missing = ["明确研究任务", "可核验的摘要或正文材料"]
    elif task_match == "mismatched":
        verdict = "method_reference" if method_terms & _paper_tokens(paper) else "not_priority"
        rationale = (
            "该论文研究任务与当前方向不同，仅在方法层面可能具有参考价值。"
            if verdict == "method_reference"
            else "该论文研究任务与当前方向不匹配。"
        )
        applicability = "如需借鉴，应在当前数据和实验设置中单独验证。"
        missing = ["当前任务下的迁移实验", "与本方向直接相关的正文证据"]
    elif evidence_level == "abstract":
        verdict = "method_reference"
        rationale = "摘要显示存在一定任务关联，但仍需正文核实方法和实验边界。"
        applicability = "可作为初步阅读线索，不等同于正文核验结论。"
        missing = ["正文方法细节", "完整实验设置"]
    else:
        verdict = "priority_read"
        rationale = "当前研究档案与论文任务存在可核验关联，且已有当前版本正文材料。"
        applicability = "可优先阅读，并结合当前数据复核适用范围。"
        missing = ["当前数据上的独立复现实验"]

    return {
        "verdict": verdict,
        "rationale": rationale,
        "task_match": task_match,
        "evidence_level": evidence_level,
        "applicability": applicability,
        "missing_information": missing,
        "evidence_refs": [
            {
                "paper_id": paper.id,
                "paper_identity": paper_identity,
                "material_identity": material_identity,
                "evidence_level": evidence_level,
            }
        ],
        "research_profile_identity": profile_identity,
        "paper_identity": paper_identity,
        "material_identity": material_identity,
        "is_current": True,
        "invalidation_reason": None,
    }


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
        material: PaperDocument | PaperSource | None = session.scalar(
            select(PaperDocument)
            .where(PaperDocument.paper_id == paper.id)
            .order_by(PaperDocument.created_at.desc(), PaperDocument.id.desc())
        )
        if material is None:
            material = session.scalar(
                select(PaperSource)
                .where(PaperSource.paper_id == paper.id)
                .order_by(PaperSource.created_at.desc(), PaperSource.id.desc())
            )
        reading_recommendation = build_reading_recommendation(
            paper=paper, profile=profile, project=project, material=material
        )
        evidence = {
            "rule_version": "recommendation-v1",
            "matched_terms": matched_sorted,
            "direction_term_count": len(direction),
            "is_fixture_sensitive": True,
            "warning": "fixture 记录仅用于演示，不可作为真实科研证据。",
            "reading_recommendation": reading_recommendation,
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
