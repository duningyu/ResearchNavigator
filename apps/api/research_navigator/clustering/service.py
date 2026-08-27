"""Versioned deterministic clustering for literature organization."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.analysis.structured import PaperAnalysisOutput
from research_navigator.models import (
    DirectionCluster,
    DirectionClusterMember,
    DirectionClusterRun,
    Paper,
    PaperAnalysisRecord,
    ResearchProject,
)

ALGORITHM_VERSION = "direction-cluster-v1"
DISCLAIMER = "Literature organization result; not an objective field taxonomy."
_DIMENSIONS = 256
_STOP = {
    "the", "a", "an", "and", "or", "for", "of", "to", "in", "with", "using",
    "on", "from", "via", "paper", "study", "method", "model",
}


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", text.casefold())
        if len(token) > 1 and token not in _STOP
    ]


def _vector(text: str) -> list[float]:
    values = [0.0] * _DIMENSIONS
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % _DIMENSIONS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        values[index] += sign
    norm = math.sqrt(sum(item * item for item in values))
    return [item / norm for item in values] if norm else values


def _cosine(left: list[float], right: list[float]) -> float:
    return max(0.0, sum(a * b for a, b in zip(left, right, strict=True)))


def cluster_documents(
    documents: dict[int, str], *, threshold: float
) -> dict[int, dict[str, object]]:
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    ids = sorted(documents)
    vectors = {paper_id: _vector(documents[paper_id]) for paper_id in ids}
    graph: dict[int, set[int]] = {paper_id: set() for paper_id in ids}
    max_similarity = {paper_id: 0.0 for paper_id in ids}
    for index, left_id in enumerate(ids):
        for right_id in ids[index + 1 :]:
            similarity = _cosine(vectors[left_id], vectors[right_id])
            max_similarity[left_id] = max(max_similarity[left_id], similarity)
            max_similarity[right_id] = max(max_similarity[right_id], similarity)
            if similarity >= threshold:
                graph[left_id].add(right_id)
                graph[right_id].add(left_id)
    components: list[list[int]] = []
    seen: set[int] = set()
    for paper_id in ids:
        if paper_id in seen:
            continue
        stack = [paper_id]
        component: list[int] = []
        seen.add(paper_id)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(graph[current], reverse=True):
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    components.sort(key=lambda group: group[0])
    result: dict[int, dict[str, object]] = {}
    cluster_number = 0
    for group in components:
        if len(group) < 2:
            paper_id = group[0]
            result[paper_id] = {
                "component": None,
                "unclustered": True,
                "similarity": round(max_similarity[paper_id], 8),
            }
            continue
        cluster_number += 1
        for paper_id in group:
            result[paper_id] = {
                "component": cluster_number,
                "unclustered": False,
                "similarity": round(max_similarity[paper_id], 8),
            }
    return {paper_id: result[paper_id] for paper_id in ids}


def _paper_text(session: Session, user_id: int, paper: Paper) -> tuple[str, str]:
    parts = [paper.title]
    for raw in (paper.fields_of_study_json, paper.concepts_json, paper.keywords_json):
        try:
            parts.extend(str(item) for item in json.loads(raw) if str(item).strip())
        except (ValueError, TypeError):
            pass
    analysis = session.scalar(
        select(PaperAnalysisRecord)
        .where(
            PaperAnalysisRecord.user_id == user_id,
            PaperAnalysisRecord.paper_id == paper.id,
        )
        .order_by(PaperAnalysisRecord.created_at.desc(), PaperAnalysisRecord.id.desc())
    )
    evidence_level = "metadata_only"
    if analysis is not None:
        parsed = PaperAnalysisOutput.model_validate_json(analysis.analysis_json)
        parts.extend(
            [
                parsed.research_problem or "",
                *parsed.core_methods,
                *parsed.datasets,
                *parsed.method_innovation,
            ]
        )
        evidence_level = parsed.evidence_level
    return " ".join(parts), evidence_level


def run_direction_clustering(
    session: Session,
    *,
    user_id: int,
    project_id: int,
    paper_ids: list[int],
    threshold: float,
) -> DirectionClusterRun:
    project = session.scalar(
        select(ResearchProject).where(
            ResearchProject.id == project_id,
            ResearchProject.user_id == user_id,
        )
    )
    if project is None:
        raise LookupError("Project not found")
    unique_ids = sorted(set(paper_ids))
    papers = [session.get(Paper, paper_id) for paper_id in unique_ids]
    if any(paper is None for paper in papers):
        raise LookupError("Paper not found")
    documents: dict[int, str] = {}
    evidence: dict[int, str] = {}
    for paper in papers:
        assert paper is not None
        text, level = _paper_text(session, user_id, paper)
        documents[paper.id] = text
        evidence[paper.id] = level
    input_contract = {
        "algorithm_version": ALGORITHM_VERSION,
        "threshold": threshold,
        "papers": [
            {
                "paper_id": paper_id,
                "text_hash": hashlib.sha256(documents[paper_id].encode("utf-8")).hexdigest(),
                "evidence_level": evidence[paper_id],
            }
            for paper_id in unique_ids
        ],
    }
    input_hash = hashlib.sha256(
        json.dumps(input_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    run = DirectionClusterRun(
        user_id=user_id,
        project_id=project_id,
        algorithm_version=ALGORITHM_VERSION,
        parameters_json=json.dumps({"threshold": threshold, "dimensions": _DIMENSIONS}),
        input_hash=input_hash,
        status="succeeded",
        disclaimer=DISCLAIMER,
    )
    session.add(run)
    session.flush()
    memberships = cluster_documents(documents, threshold=threshold)
    grouped: dict[int, list[int]] = defaultdict(list)
    for paper_id, item in memberships.items():
        if item["component"] is not None:
            grouped[int(item["component"])].append(paper_id)
    clusters: dict[int, DirectionCluster] = {}
    for component, member_ids in sorted(grouped.items()):
        term_counts: Counter[str] = Counter()
        evidence_counts: Counter[str] = Counter()
        for paper_id in member_ids:
            term_counts.update(_tokens(documents[paper_id]))
            evidence_counts[evidence[paper_id]] += 1
        terms = [term for term, _ in sorted(term_counts.items(), key=lambda x: (-x[1], x[0]))[:5]]
        cluster = DirectionCluster(
            run_id=run.id,
            cluster_key=f"c{component:03d}",
            label=" / ".join(terms[:3]) or f"Cluster {component}",
            terms_json=json.dumps(terms, ensure_ascii=False),
            evidence_distribution_json=json.dumps(dict(evidence_counts), ensure_ascii=False),
        )
        session.add(cluster)
        session.flush()
        clusters[component] = cluster
    for paper_id in unique_ids:
        item = memberships[paper_id]
        component = item["component"]
        session.add(
            DirectionClusterMember(
                run_id=run.id,
                cluster_id=clusters[int(component)].id if component is not None else None,
                paper_id=paper_id,
                similarity=float(item["similarity"]),
                is_unclustered=bool(item["unclustered"]),
            )
        )
    session.flush()
    return run
