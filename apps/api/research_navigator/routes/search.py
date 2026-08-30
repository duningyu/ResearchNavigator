"""Federated paper search, resolution, and conservative related-paper endpoints."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_user, get_db
from research_navigator.models import Paper, ResearchProject, SearchSession, SourceRequest, User
from research_navigator.schemas.search import (
    PaperRead,
    PaperResolveRequest,
    RankingMetadata,
    RelatedPaperRead,
    SearchPaperRequest,
    SearchResponse,
    SearchSessionRead,
)
from research_navigator.scholarly.base import PaperRecord, SearchRequest, SourceStatus
from research_navigator.scholarly.normalize import (
    normalize_arxiv_id,
    normalize_doi,
    normalize_title,
)
from research_navigator.scholarly.ranking import (
    RANKING_RULE_VERSION,
    RankedRecord,
    classify_search_mode,
    rank_discovery,
    relevance_score,
    search_mode_rule_version,
)
from research_navigator.scholarly.repository import paper_to_read, upsert_paper
from research_navigator.scholarly.runtime import SourceRuntimeRepository
from research_navigator.scholarly.service import FederatedSearchService

router = APIRouter(tags=["search"])
_TOKEN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", re.IGNORECASE)
_STOP = {"the", "and", "for", "with", "from", "using", "based", "time", "series", "paper"}


def _session_read(row: SearchSession) -> SearchSessionRead:
    return SearchSessionRead(
        id=row.id,
        project_id=row.project_id,
        query=row.query,
        filters=json.loads(row.filters_json),
        source_status=json.loads(row.source_status_json),
        result_ids=json.loads(row.result_ids_json),
        result_count=row.result_count,
        search_mode=row.search_mode,
        diversity_seed=row.diversity_seed,
        ranking_rule_version=row.ranking_rule_version,
        composition=json.loads(row.composition_json),
        created_at=row.created_at,
    )


def _persist_source_requests(
    session: Session,
    *,
    user: User,
    project_id: int | None,
    request_payload: SearchRequest,
    source_status: dict[str, SourceStatus],
    papers: list[PaperRecord],
) -> None:
    finished = datetime.now(UTC)
    by_source: dict[str, list[dict[str, object]]] = {name: [] for name in source_status}
    for paper in papers:
        for provenance in paper.source_provenance:
            if provenance.source not in by_source:
                continue
            by_source[provenance.source].append(
                {
                    "source_id": provenance.source_id,
                    "source_url": provenance.source_url,
                    "raw_hash": provenance.raw_hash,
                    "fetched_at": provenance.fetched_at.isoformat(),
                    "is_fixture": provenance.is_fixture,
                }
            )
    for name, status_value in source_status.items():
        status_payload: dict[str, object] = status_value.model_dump(mode="json")
        source_records = by_source.get(name, [])
        aggregate_material = json.dumps(
            [item.get("raw_hash") for item in source_records],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        status_payload["raw_response_hash"] = hashlib.sha256(aggregate_material).hexdigest()
        status_payload["audit_semantics"] = (
            "aggregate hash of persisted per-record raw hashes; not a byte-for-byte HTTP body hash"
        )
        session.add(
            SourceRequest(
                user_id=user.id,
                project_id=project_id,
                source=name,
                query=request_payload.query,
                request_json=json.dumps(
                    request_payload.model_dump(mode="json"), ensure_ascii=False
                ),
                response_metadata_json=json.dumps(status_payload, ensure_ascii=False),
                source_records_json=json.dumps(source_records, ensure_ascii=False),
                status=str(status_payload.get("status", "error")),
                error=(
                    str(status_payload.get("detail"))
                    if status_payload.get("status") not in {"ok", "disabled", "not_configured"}
                    and status_payload.get("detail")
                    else None
                ),
                started_at=finished,
                finished_at=finished,
            )
        )


def _validate_project(session: Session, *, user_id: int, project_id: int | None) -> None:
    if project_id is None:
        return
    owned = session.scalar(
        select(ResearchProject.id).where(
            ResearchProject.id == project_id, ResearchProject.user_id == user_id
        )
    )
    if owned is None:
        raise HTTPException(status_code=404, detail="Project not found")


async def _perform_search(
    *,
    payload: SearchPaperRequest,
    request: Request,
    user: User,
    session: Session,
    diversity_seed: str | None = None,
) -> SearchResponse:
    settings = request.app.state.settings
    if settings.public_demo_mode and len(payload.query) > settings.public_demo_max_query_length:
        raise HTTPException(status_code=422, detail="PUBLIC_DEMO_QUERY_TOO_LONG")
    _validate_project(session, user_id=user.id, project_id=payload.project_id)
    search_mode = classify_search_mode(payload.query, payload.mode)
    seed = diversity_seed or (secrets.token_hex(16) if search_mode == "discovery" else None)
    fetch_limit = min(
        100, max(payload.limit, payload.limit * 2 if search_mode == "discovery" else payload.limit)
    )
    service_payload = SearchRequest.model_validate(
        {**payload.model_dump(mode="json", exclude={"mode"}), "limit": fetch_limit}
    )
    service: FederatedSearchService = request.app.state.search_service
    runtime = SourceRuntimeRepository(session)
    requested_names = service_payload.sources or list(service.adapters)
    active_names: list[str] = []
    blocked_status: dict[str, SourceStatus] = {}
    for source_name in requested_names:
        blocked = runtime.before_call(source_name)
        if blocked is None:
            active_names.append(source_name)
        else:
            blocked_status[source_name] = blocked
    result = await service.search(service_payload, selected_names=active_names)
    result.source_status.update(blocked_status)
    for source_name, source_status in result.source_status.items():
        if source_name not in blocked_status:
            runtime.after_call(source_name, source_status)
    _persist_source_requests(
        session,
        user=user,
        project_id=payload.project_id,
        request_payload=service_payload,
        source_status=result.source_status,
        papers=result.papers,
    )

    if search_mode == "discovery":
        ranked, composition_model = rank_discovery(
            result.papers, query=payload.query, limit=payload.limit, seed=seed or ""
        )
        composition: dict[str, object] = composition_model.as_dict()
        ranking_rule_version = RANKING_RULE_VERSION
    else:
        sorted_records = sorted(
            result.papers, key=lambda record: relevance_score(record, payload.query), reverse=True
        )[: payload.limit]
        ranked = [
            RankedRecord(
                record=record,
                label="precise_result",
                relevance=relevance_score(record, payload.query),
                rank_score=relevance_score(record, payload.query),
                relevance_band=int(relevance_score(record, payload.query) * 100),
            )
            for record in sorted_records
        ]
        composition = {
            "requested_limit": payload.limit,
            "result_count": len(ranked),
            "mode_rule_version": search_mode_rule_version(),
        }
        ranking_rule_version = "precise-ranking-v1"

    paper_models = [upsert_paper(session, item.record) for item in ranked]
    rankings: dict[str, dict[str, object]] = {}
    paper_reads: list[PaperRead] = []
    for position, (paper, ranked_item) in enumerate(
        zip(paper_models, ranked, strict=True), start=1
    ):
        metadata = RankingMetadata(
            label=ranked_item.label,
            relevance=round(ranked_item.relevance, 6),
            rank_score=round(ranked_item.rank_score, 6),
            relevance_band=ranked_item.relevance_band,
            position=position,
        )
        rankings[str(paper.id)] = metadata.model_dump(mode="json")
        paper_reads.append(paper_to_read(session, paper).model_copy(update={"ranking": metadata}))
    composition["rankings"] = rankings
    composition["mode_rule_version"] = search_mode_rule_version()

    search_session = SearchSession(
        user_id=user.id,
        project_id=payload.project_id,
        query=payload.query,
        filters_json=json.dumps(payload.model_dump(mode="json"), ensure_ascii=False),
        source_status_json=json.dumps(
            {key: value.model_dump(mode="json") for key, value in result.source_status.items()},
            ensure_ascii=False,
        ),
        result_ids_json=json.dumps([paper.id for paper in paper_models]),
        result_count=len(paper_models),
        search_mode=search_mode,
        ranking_rule_version=ranking_rule_version,
        diversity_seed=seed,
        composition_json=json.dumps(composition, ensure_ascii=False),
    )
    session.add(search_session)
    session.commit()
    session.refresh(search_session)
    return SearchResponse(
        session_id=search_session.id,
        result_count=len(paper_models),
        source_status=result.source_status,
        search_mode=search_mode,
        diversity_seed=seed,
        ranking_rule_version=ranking_rule_version,
        composition=composition,
        papers=paper_reads,
    )


@router.post("/search/papers", response_model=SearchResponse)
async def search_papers(
    payload: SearchPaperRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> SearchResponse:
    return await _perform_search(payload=payload, request=request, user=user, session=session)


@router.get("/search/sessions", response_model=list[SearchSessionRead])
def list_search_sessions(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> list[SearchSessionRead]:
    rows = list(
        session.scalars(
            select(SearchSession)
            .where(SearchSession.user_id == user.id)
            .order_by(SearchSession.created_at.desc())
        )
    )
    return [_session_read(row) for row in rows]


@router.get("/search/sessions/{session_id}", response_model=SearchSessionRead)
def get_search_session(
    session_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> SearchSessionRead:
    row = session.scalar(
        select(SearchSession).where(
            SearchSession.id == session_id, SearchSession.user_id == user.id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Search session not found")
    return _session_read(row)


@router.post("/search/sessions/{session_id}/rerun", response_model=SearchResponse)
async def rerun_search_session(
    session_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> SearchResponse:
    row = session.scalar(
        select(SearchSession).where(
            SearchSession.id == session_id, SearchSession.user_id == user.id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Search session not found")
    try:
        payload = SearchPaperRequest.model_validate(json.loads(row.filters_json))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=409, detail="Saved search filters are invalid") from exc
    return await _perform_search(
        payload=payload,
        request=request,
        user=user,
        session=session,
        diversity_seed=row.diversity_seed,
    )


@router.get("/search/sessions/{session_id}/papers", response_model=list[PaperRead])
def get_search_session_papers(
    session_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[PaperRead]:
    row = session.scalar(
        select(SearchSession).where(
            SearchSession.id == session_id, SearchSession.user_id == user.id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Search session not found")
    result_ids = [int(item) for item in json.loads(row.result_ids_json)]
    papers_by_id = {
        paper.id: paper for paper in session.scalars(select(Paper).where(Paper.id.in_(result_ids)))
    }
    composition = json.loads(row.composition_json)
    rankings = composition.get("rankings", {}) if isinstance(composition, dict) else {}
    output: list[PaperRead] = []
    for paper_id in result_ids:
        paper = papers_by_id.get(paper_id)
        if paper is None:
            continue
        ranking_payload = rankings.get(str(paper_id)) if isinstance(rankings, dict) else None
        ranking = RankingMetadata.model_validate(ranking_payload) if ranking_payload else None
        output.append(paper_to_read(session, paper).model_copy(update={"ranking": ranking}))
    return output


@router.get("/papers/{paper_id}", response_model=PaperRead)
def get_paper(
    paper_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> PaperRead:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper_to_read(session, paper)


@router.post("/papers/resolve", response_model=PaperRead)
async def resolve_paper(
    payload: PaperResolveRequest,
    request: Request,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> PaperRead:
    conditions = []
    doi = normalize_doi(payload.doi)
    arxiv_id = normalize_arxiv_id(payload.arxiv_id)
    if doi:
        conditions.append(Paper.doi == doi)
    if arxiv_id:
        conditions.append(Paper.arxiv_id == arxiv_id)
    if payload.title:
        title_condition = Paper.normalized_title == normalize_title(payload.title)
        if payload.publication_year is not None:
            conditions.append(
                (title_condition) & (Paper.publication_year == payload.publication_year)
            )
        else:
            conditions.append(title_condition)
    if conditions:
        local = session.scalar(select(Paper).where(or_(*conditions)).order_by(Paper.id))
        if local is not None:
            return paper_to_read(session, local)

    if doi is not None:
        exact_service: FederatedSearchService = request.app.state.search_service
        exact = await exact_service.resolve_exact(doi, selected_names=payload.sources or None)
        if exact is not None:
            paper = upsert_paper(session, exact)
            session.commit()
            return paper_to_read(session, paper)
        raise HTTPException(
            status_code=404, detail="Paper could not be resolved from configured sources"
        )

    query = payload.doi or payload.arxiv_id or payload.title or ""
    service: FederatedSearchService = request.app.state.search_service
    result = await service.search(SearchRequest(query=query, limit=10, sources=payload.sources))
    expected_title = normalize_title(payload.title) if payload.title else None
    for record in result.papers:
        normalized_doi = normalize_doi(record.doi)
        normalized_arxiv = normalize_arxiv_id(record.arxiv_id)
        normalized_record_title = normalize_title(record.title)
        matched = (
            (doi is not None and normalized_doi == doi)
            or (arxiv_id is not None and normalized_arxiv == arxiv_id)
            or (
                expected_title is not None
                and normalized_record_title == expected_title
                and (
                    payload.publication_year is None
                    or record.publication_year == payload.publication_year
                )
            )
        )
        if matched:
            paper = upsert_paper(session, record)
            session.commit()
            return paper_to_read(session, paper)
    raise HTTPException(
        status_code=404, detail="Paper could not be resolved from configured sources"
    )


def _paper_terms(paper: Paper) -> set[str]:
    values = [paper.title, paper.abstract or ""]
    for raw in (paper.keywords_json, paper.concepts_json, paper.fields_of_study_json):
        try:
            values.extend(str(item) for item in json.loads(raw))
        except (ValueError, TypeError):
            continue
    return {
        token.lower() for token in _TOKEN.findall(" ".join(values)) if token.lower() not in _STOP
    }


@router.get("/papers/{paper_id}/related", response_model=list[RelatedPaperRead])
def related_papers(
    paper_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[RelatedPaperRead]:
    target = session.get(Paper, paper_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    target_terms = _paper_terms(target)
    scored: list[tuple[float, Paper, list[str]]] = []
    for candidate in session.scalars(select(Paper).where(Paper.id != paper_id)):
        candidate_terms = _paper_terms(candidate)
        shared = sorted(target_terms & candidate_terms)
        if not shared:
            continue
        union = target_terms | candidate_terms
        score = round(len(shared) / max(1, len(union)), 6)
        scored.append((score, candidate, shared))
    scored.sort(key=lambda row: (row[0], row[1].publication_year or 0), reverse=True)
    return [
        RelatedPaperRead(
            paper=paper_to_read(session, paper),
            score=score,
            rationale=f"共享术语：{', '.join(shared[:10])}。这是本地内容相似度，不代表引用关系。",
            shared_terms=shared,
        )
        for score, paper, shared in scored[:limit]
    ]
