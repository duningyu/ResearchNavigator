"""Dataset mention extraction that never fills absent scholarly facts."""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.analysis.structured import PaperAnalysisOutput
from research_navigator.models import DatasetCard, PaperAnalysisRecord, PaperDatasetMention

_FULLTEXT_LEVELS = {
    "open_fulltext",
    "user_uploaded_fulltext",
    "publisher_authorized_fulltext",
}


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def extract_split_evidence(
    *, evidence_level: str, protocol: list[str]
) -> dict[str, str | None]:
    result: dict[str, str | None] = {
        "train_split": None,
        "validation_split": None,
        "test_split": None,
    }
    if evidence_level not in _FULLTEXT_LEVELS:
        return result
    for sentence in protocol:
        lower = sentence.casefold()
        if result["train_split"] is None and any(
            term in lower for term in ("train split", "training split", "training set")
        ):
            result["train_split"] = sentence
        if result["validation_split"] is None and any(
            term in lower for term in ("validation split", "validation set", "development set")
        ):
            result["validation_split"] = sentence
        if result["test_split"] is None and any(
            term in lower for term in ("test split", "testing split", "test set")
        ):
            result["test_split"] = sentence
    return result


def refresh_dataset_cards(
    session: Session, analysis_record: PaperAnalysisRecord
) -> list[PaperDatasetMention]:
    analysis = PaperAnalysisOutput.model_validate_json(analysis_record.analysis_json)
    for old in list(
        session.scalars(
            select(PaperDatasetMention).where(
                PaperDatasetMention.analysis_id == analysis_record.id
            )
        )
    ):
        session.delete(old)
    session.flush()

    split_evidence = extract_split_evidence(
        evidence_level=analysis.evidence_level,
        protocol=analysis.experimental_protocol,
    )
    citation_payload = {
        field: [citation.model_dump(mode="json") for citation in citations]
        for field, citations in analysis.field_citations.items()
        if field in {"datasets", "metrics", "experimental_protocol"}
    }
    mentions: list[PaperDatasetMention] = []
    for raw_name in dict.fromkeys(name.strip() for name in analysis.datasets if name.strip()):
        normalized = _normalize_name(raw_name)
        card = session.scalar(
            select(DatasetCard).where(DatasetCard.normalized_name == normalized)
        )
        if card is None:
            card = DatasetCard(
                canonical_name=raw_name,
                normalized_name=normalized,
                access_url=None,
                license=None,
                domain=None,
                identity_status="mentioned_only",
                provenance_json=json.dumps(
                    [
                        {
                            "analysis_id": analysis_record.id,
                            "paper_id": analysis_record.paper_id,
                            "field": "datasets",
                            "evidence_level": analysis.evidence_level,
                        }
                    ],
                    ensure_ascii=False,
                ),
            )
            session.add(card)
            session.flush()
        mention = PaperDatasetMention(
            user_id=analysis_record.user_id,
            paper_id=analysis_record.paper_id,
            analysis_id=analysis_record.id,
            dataset_id=card.id,
            raw_mention=raw_name,
            role=None,
            task=None,
            train_split=split_evidence["train_split"],
            validation_split=split_evidence["validation_split"],
            test_split=split_evidence["test_split"],
            metrics_json=json.dumps(analysis.metrics, ensure_ascii=False),
            evidence_level=analysis.evidence_level,
            field_citations_json=json.dumps(citation_payload, ensure_ascii=False),
            identity_status=card.identity_status,
        )
        session.add(mention)
        session.flush()
        mentions.append(mention)
    return mentions
