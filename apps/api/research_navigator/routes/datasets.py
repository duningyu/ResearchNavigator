"""Dataset card endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.datasets.service import refresh_dataset_cards
from research_navigator.deps import get_current_user, get_db
from research_navigator.models import (
    DatasetCard,
    Paper,
    PaperAnalysisRecord,
    PaperDatasetMention,
    User,
)
from research_navigator.schemas.datasets import DatasetCardRead

router = APIRouter(tags=["datasets"])


def _read(card: DatasetCard, mention: PaperDatasetMention | None = None) -> DatasetCardRead:
    return DatasetCardRead(
        id=card.id,
        canonical_name=card.canonical_name,
        access_url=card.access_url,
        license=card.license,
        domain=card.domain,
        identity_status=card.identity_status,
        provenance=json.loads(card.provenance_json),
        mention_id=mention.id if mention is not None else None,
        paper_id=mention.paper_id if mention is not None else None,
        analysis_id=mention.analysis_id if mention is not None else None,
        raw_mention=mention.raw_mention if mention is not None else None,
        role=mention.role if mention is not None else None,
        task=mention.task if mention is not None else None,
        train_split=mention.train_split if mention is not None else None,
        validation_split=mention.validation_split if mention is not None else None,
        test_split=mention.test_split if mention is not None else None,
        metrics=json.loads(mention.metrics_json) if mention is not None else [],
        evidence_level=mention.evidence_level if mention is not None else None,
        field_citations=(
            json.loads(mention.field_citations_json) if mention is not None else {}
        ),
    )


def _paper_mentions(session: Session, user_id: int, paper_id: int) -> list[PaperDatasetMention]:
    return list(
        session.scalars(
            select(PaperDatasetMention)
            .where(
                PaperDatasetMention.user_id == user_id,
                PaperDatasetMention.paper_id == paper_id,
            )
            .order_by(PaperDatasetMention.id)
        )
    )


@router.post("/papers/{paper_id}/datasets/refresh", response_model=list[DatasetCardRead])
def refresh_paper_datasets(
    paper_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[DatasetCardRead]:
    if session.get(Paper, paper_id) is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    analysis = session.scalar(
        select(PaperAnalysisRecord)
        .where(
            PaperAnalysisRecord.user_id == user.id,
            PaperAnalysisRecord.paper_id == paper_id,
        )
        .order_by(PaperAnalysisRecord.created_at.desc(), PaperAnalysisRecord.id.desc())
    )
    if analysis is None:
        raise HTTPException(status_code=409, detail="Run paper analysis before dataset refresh")
    refresh_dataset_cards(session, analysis)
    session.commit()
    return list_paper_datasets(paper_id, user, session)


@router.get("/papers/{paper_id}/datasets", response_model=list[DatasetCardRead])
def list_paper_datasets(
    paper_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[DatasetCardRead]:
    if session.get(Paper, paper_id) is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    result: list[DatasetCardRead] = []
    for mention in _paper_mentions(session, user.id, paper_id):
        card = session.get(DatasetCard, mention.dataset_id) if mention.dataset_id else None
        if card is not None:
            result.append(_read(card, mention))
    return result


@router.get("/datasets/{dataset_id}", response_model=DatasetCardRead)
def get_dataset(
    dataset_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> DatasetCardRead:
    mention = session.scalar(
        select(PaperDatasetMention)
        .where(
            PaperDatasetMention.user_id == user.id,
            PaperDatasetMention.dataset_id == dataset_id,
        )
        .order_by(PaperDatasetMention.id.desc())
    )
    if mention is None:
        raise HTTPException(status_code=404, detail="Dataset card not found")
    card = session.get(DatasetCard, dataset_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Dataset card not found")
    return _read(card, mention)
