"""Build and persist evidence-aware comparison matrices from explicit paper sets."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.analysis.matching import WeightedScoreResult
from research_navigator.analysis.service import run_paper_analysis
from research_navigator.analysis.structured import PaperAnalysisOutput
from research_navigator.models import (
    ComparisonRun,
    Paper,
    PaperAnalysisRecord,
    PaperSet,
    PaperSetItem,
    ResearchProfile,
    ResearchProject,
)


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _direction_snapshot(
    project: ResearchProject, profile: ResearchProfile | None
) -> dict[str, Any]:
    profile_payload: dict[str, Any] | None = None
    if profile is not None:
        profile_payload = {
            "stage": profile.stage,
            "major": profile.major,
            "broad_direction": profile.broad_direction,
            "keywords": json.loads(profile.keywords_json),
            "excluded_terms": json.loads(profile.excluded_terms_json),
            "preferences": json.loads(profile.preferences_json),
            "compute_constraints": profile.compute_constraints,
        }
    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "broad_direction": project.broad_direction,
        },
        "profile": profile_payload,
    }


ROW_SPECS: tuple[tuple[str, str], ...] = (
    ("research_problem", "研究问题与任务定义"),
    ("task_definition", "输入 / 输出 / 场景"),
    ("core_methods", "核心方法"),
    ("method_innovation", "方法创新"),
    ("theoretical_contribution", "理论创新/理论贡献"),
    ("research_route", "研究路线"),
    ("new_modules", "新增模块"),
    ("datasets", "数据集"),
    ("baselines", "对比基线"),
    ("metrics", "评价指标"),
    ("experimental_protocol", "标签、切分与实验协议"),
    ("major_results", "主要实验结果"),
    ("claimed_contributions", "作者声明贡献"),
    ("future_work_explicit", "明确 Future Work"),
    ("limitations_author_stated", "作者明确局限"),
    ("limitations_inferred", "系统推断局限"),
    ("missing_fields", "缺失字段"),
    ("evidence_level", "证据等级"),
    ("direction_relevance", "与当前研究方向关联度"),
)


def _latest_analysis(
    session: Session, *, user_id: int, project_id: int, paper_id: int
) -> PaperAnalysisRecord:
    row = session.scalar(
        select(PaperAnalysisRecord)
        .where(
            PaperAnalysisRecord.user_id == user_id,
            PaperAnalysisRecord.paper_id == paper_id,
            PaperAnalysisRecord.project_id == project_id,
        )
        .order_by(PaperAnalysisRecord.created_at.desc(), PaperAnalysisRecord.id.desc())
    )
    if row is None:
        row = run_paper_analysis(
            session,
            user_id=user_id,
            paper_id=paper_id,
            project_id=project_id,
        )
    return row


def _comparison_cell(
    *, paper_id: int, field: str, analysis: PaperAnalysisOutput, direction: WeightedScoreResult
) -> dict[str, Any]:
    if field == "direction_relevance":
        return {
            "paper_id": paper_id,
            "value": direction.model_dump(mode="json"),
            "evidence_state": "evidenced" if direction.evidence_coverage > 0 else "unknown",
            "citations": [item.model_dump(mode="json") for item in analysis.citations],
        }
    if field == "evidence_level":
        return {
            "paper_id": paper_id,
            "value": analysis.evidence_level,
            "evidence_state": "evidenced",
            "citations": [item.model_dump(mode="json") for item in analysis.citations],
        }
    if field == "missing_fields":
        return {
            "paper_id": paper_id,
            "value": analysis.missing_fields,
            "evidence_state": "evidenced",
            "citations": [],
        }
    value = getattr(analysis, field)
    state = analysis.field_states.get(field, "unknown")
    citations = [item.model_dump(mode="json") for item in analysis.field_citations.get(field, [])]
    return {
        "paper_id": paper_id,
        "value": value.model_dump(mode="json") if hasattr(value, "model_dump") else value,
        "evidence_state": state,
        "citations": citations,
    }


def create_comparison(
    session: Session, *, user_id: int, project_id: int, paper_set_id: int
) -> ComparisonRun:
    project = session.scalar(
        select(ResearchProject).where(
            ResearchProject.id == project_id, ResearchProject.user_id == user_id
        )
    )
    if project is None:
        raise LookupError("Project not found")
    paper_set = session.scalar(
        select(PaperSet).where(PaperSet.id == paper_set_id, PaperSet.user_id == user_id)
    )
    if paper_set is None:
        raise LookupError("Paper set not found")
    if paper_set.project_id is not None and paper_set.project_id != project_id:
        raise ValueError("Paper set belongs to a different project")
    items = list(
        session.scalars(
            select(PaperSetItem)
            .where(PaperSetItem.paper_set_id == paper_set.id)
            .order_by(PaperSetItem.position)
        )
    )
    if len(items) < 2:
        raise ValueError("At least two explicitly selected papers are required")

    papers_by_id = {
        paper.id: paper
        for paper in session.scalars(
            select(Paper).where(Paper.id.in_([item.paper_id for item in items]))
        )
    }
    profile = session.scalar(select(ResearchProfile).where(ResearchProfile.user_id == user_id))
    direction_snapshot = _direction_snapshot(project, profile)
    analyses: dict[int, tuple[PaperAnalysisOutput, WeightedScoreResult]] = {}
    paper_payloads: list[dict[str, Any]] = []
    versions: set[str] = set()
    for item in items:
        paper = papers_by_id.get(item.paper_id)
        if paper is None:
            raise LookupError("One or more papers were not found")
        record = _latest_analysis(
            session, user_id=user_id, project_id=project_id, paper_id=paper.id
        )
        analysis = PaperAnalysisOutput.model_validate_json(record.analysis_json)
        direction = WeightedScoreResult.model_validate_json(record.direction_similarity_json)
        analyses[paper.id] = (analysis, direction)
        versions.add(analysis.analysis_version)
        paper_payloads.append(
            {
                "id": paper.id,
                "title": paper.title,
                "publication_year": paper.publication_year,
                "venue": paper.venue,
                "evidence_level": analysis.evidence_level,
            }
        )

    rows: list[dict[str, Any]] = []
    for key, label in ROW_SPECS:
        rows.append(
            {
                "key": key,
                "label": label,
                "cells": [
                    _comparison_cell(
                        paper_id=item.paper_id,
                        field=key,
                        analysis=analyses[item.paper_id][0],
                        direction=analyses[item.paper_id][1],
                    )
                    for item in items
                ],
            }
        )

    matrix = {
        "papers": paper_payloads,
        "rows": rows,
    }
    evidence_payload = {
        "paper_set_id": paper_set.id,
        "direction_snapshot": direction_snapshot,
        "matrix": matrix,
    }
    evidence_hash = hashlib.sha256(_canonical(evidence_payload).encode()).hexdigest()
    analysis_version = "+".join(sorted(versions)) or "unknown"
    row = ComparisonRun(
        user_id=user_id,
        project_id=project_id,
        paper_set_id=paper_set.id,
        direction_snapshot_json=_canonical(direction_snapshot),
        matrix_json=_canonical(matrix),
        analysis_version=analysis_version,
        evidence_hash=evidence_hash,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
