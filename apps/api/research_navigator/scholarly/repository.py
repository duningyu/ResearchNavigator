"""Persistence bridge from normalized scholarly records to SQL models."""

from __future__ import annotations

import json
from collections import OrderedDict

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from research_navigator.models import Paper, PaperSource
from research_navigator.schemas.search import PaperRead
from research_navigator.scholarly.base import PaperRecord, SourceProvenance
from research_navigator.scholarly.normalize import normalize_record


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _find_existing(session: Session, record: PaperRecord) -> Paper | None:
    conditions = []
    if record.doi:
        conditions.append(Paper.doi == record.doi)
    if record.arxiv_id:
        conditions.append(Paper.arxiv_id == record.arxiv_id)
    if conditions:
        found = session.scalar(select(Paper).where(or_(*conditions)))
        if found is not None:
            return found
    return session.scalar(
        select(Paper).where(
            Paper.normalized_title == record.normalized_title,
            Paper.publication_year == record.publication_year,
        )
    )


def upsert_paper(session: Session, raw_record: PaperRecord) -> Paper:
    record = normalize_record(raw_record)
    paper = _find_existing(session, record)
    authors = [author.model_dump(mode="json") for author in record.authors]
    selected_abstract_provenance = None
    if paper is None:
        paper = Paper(
            title=record.title,
            normalized_title=record.normalized_title or "",
            translated_title=record.translated_title,
            abstract=record.abstract,
            publication_year=record.publication_year,
            publication_date_text=record.publication_date.isoformat()
            if record.publication_date
            else None,
            authors_json=_json(authors),
            venue=record.venue,
            venue_type=record.venue_type,
            doi=record.doi,
            arxiv_id=record.arxiv_id,
            external_ids_json=_json(record.external_ids),
            source_urls_json=_json(record.source_urls),
            publisher_url=record.publisher_url,
            pdf_url=record.pdf_url,
            open_access_status=record.open_access_status,
            citation_count=record.citation_count,
            reference_count=record.reference_count,
            fields_of_study_json=_json(record.fields_of_study),
            concepts_json=_json(record.concepts),
            keywords_json=_json(record.keywords),
        )
        session.add(paper)
        session.flush()
        if record.abstract:
            selected_abstract_provenance = record.abstract_provenance
    else:
        # Keep conflicting material versions explicit; do not bless an old PDF
        # as the newly observed version or merge preprint/publication evidence.
        identities = json.loads(paper.external_ids_json or "{}")
        incoming_version = record.external_ids.get("arxiv_versioned_id")
        previous_version = identities.get("arxiv_versioned_id")
        if incoming_version and previous_version and incoming_version != previous_version:
            observed = set(identities.get("arxiv_observed_versions", []))
            observed.update((previous_version, incoming_version))
            identities["arxiv_observed_versions"] = sorted(observed)
            identities["arxiv_version_conflict"] = True
            paper.external_ids_json = _json(identities)
        current_abstract_verified = session.scalar(
            select(PaperSource.id).where(
                PaperSource.paper_id == paper.id,
                PaperSource.provides_abstract.is_(True),
                PaperSource.is_fixture.is_(False),
            )
        ) is not None
        incoming_abstract_verified = bool(
            record.abstract_provenance and not record.abstract_provenance.is_fixture
        )
        should_replace_abstract = bool(
            record.abstract
            and (
                not paper.abstract
                or (incoming_abstract_verified and not current_abstract_verified)
                or (
                    incoming_abstract_verified == current_abstract_verified
                    and len(record.abstract) > len(paper.abstract)
                )
            )
        )
        if should_replace_abstract:
            paper.abstract = record.abstract
            selected_abstract_provenance = record.abstract_provenance
            for source_row in session.scalars(
                select(PaperSource).where(PaperSource.paper_id == paper.id)
            ):
                source_row.provides_abstract = False
        paper.translated_title = paper.translated_title or record.translated_title
        paper.venue = paper.venue or record.venue
        paper.venue_type = paper.venue_type or record.venue_type
        paper.doi = paper.doi or record.doi
        paper.arxiv_id = paper.arxiv_id or record.arxiv_id
        paper.publisher_url = paper.publisher_url or record.publisher_url
        paper.pdf_url = paper.pdf_url or record.pdf_url
        paper.open_access_status = paper.open_access_status or record.open_access_status
        paper.citation_count = max(
            [item for item in (paper.citation_count, record.citation_count) if item is not None],
            default=None,
        )
        paper.reference_count = max(
            [item for item in (paper.reference_count, record.reference_count) if item is not None],
            default=None,
        )
        existing_urls = json.loads(paper.source_urls_json)
        paper.source_urls_json = _json(
            list(OrderedDict.fromkeys(existing_urls + record.source_urls))
        )

    for provenance in record.source_provenance:
        provides_abstract = bool(
            selected_abstract_provenance
            and provenance.source == selected_abstract_provenance.source
            and provenance.source_id == selected_abstract_provenance.source_id
        )
        existing_source = session.scalar(
            select(PaperSource).where(
                PaperSource.paper_id == paper.id,
                PaperSource.source == provenance.source,
                PaperSource.source_id == provenance.source_id,
            )
        )
        if existing_source is None:
            session.add(
                PaperSource(
                    paper_id=paper.id,
                    source=provenance.source,
                    source_id=provenance.source_id,
                    source_url=provenance.source_url,
                    raw_hash=provenance.raw_hash,
                    is_fixture=provenance.is_fixture,
                    provides_abstract=provides_abstract,
                    fetched_at=provenance.fetched_at,
                )
            )
        elif provides_abstract:
            existing_source.provides_abstract = True
    session.flush()
    return paper


def paper_to_read(session: Session, paper: Paper) -> PaperRead:
    source_rows = list(session.scalars(select(PaperSource).where(PaperSource.paper_id == paper.id)))
    provenance = [
        SourceProvenance(
            source=row.source,
            source_id=row.source_id,
            source_url=row.source_url,
            raw_hash=row.raw_hash,
            is_fixture=row.is_fixture,
            fetched_at=row.fetched_at,
        )
        for row in source_rows
    ]
    return PaperRead(
        id=paper.id,
        title=paper.title,
        normalized_title=paper.normalized_title,
        translated_title=paper.translated_title,
        abstract=paper.abstract,
        publication_year=paper.publication_year,
        publication_date=paper.publication_date_text,
        authors=json.loads(paper.authors_json),
        venue=paper.venue,
        venue_type=paper.venue_type,
        doi=paper.doi,
        arxiv_id=paper.arxiv_id,
        external_ids=json.loads(paper.external_ids_json),
        source_urls=json.loads(paper.source_urls_json),
        publisher_url=paper.publisher_url,
        pdf_url=paper.pdf_url,
        open_access_status=paper.open_access_status,
        citation_count=paper.citation_count,
        reference_count=paper.reference_count,
        fields_of_study=json.loads(paper.fields_of_study_json),
        concepts=json.loads(paper.concepts_json),
        keywords=json.loads(paper.keywords_json),
        source_provenance=provenance,
        is_fixture=any(item.is_fixture for item in provenance),
        abstract_evidence_verified=any(
            row.provides_abstract and not row.is_fixture for row in source_rows
        ),
    )
