"""Conservative author identity resolution from persisted scholarly metadata."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.models import (
    Author,
    AuthorSourceRecord,
    Paper,
    PaperAuthorLink,
    PaperSource,
)


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).casefold()


def _normalize_orcid(orcid: str | None) -> str | None:
    if not orcid:
        return None
    value = orcid.strip().removeprefix("https://orcid.org/").removeprefix("http://orcid.org/")
    return value or None


def canonical_author_identity(
    *,
    name: str,
    orcid: str | None,
    source: str | None,
    source_author_id: str | None,
    paper_id: int | None = None,
    position: int | None = None,
) -> str:
    normalized_orcid = _normalize_orcid(orcid)
    if normalized_orcid:
        return f"orcid:{normalized_orcid}"
    if source and source_author_id:
        return f"source:{source}:{source_author_id}"
    return f"unresolved:{paper_id}:{position}:{_normalize_name(name)}"


def _paper_source(session: Session, paper_id: int) -> PaperSource | None:
    return session.scalar(
        select(PaperSource)
        .where(PaperSource.paper_id == paper_id, PaperSource.is_fixture.is_(False))
        .order_by(PaperSource.fetched_at.desc(), PaperSource.id.desc())
    ) or session.scalar(
        select(PaperSource).where(PaperSource.paper_id == paper_id).order_by(PaperSource.id)
    )


def refresh_author_cards(session: Session, paper: Paper) -> list[Author]:
    raw_authors = json.loads(paper.authors_json or "[]")
    if not isinstance(raw_authors, list):
        raw_authors = []
    source_row = _paper_source(session, paper.id)
    source = source_row.source if source_row is not None else None
    existing_links = {
        link.position: link
        for link in session.scalars(
            select(PaperAuthorLink).where(PaperAuthorLink.paper_id == paper.id)
        )
    }
    result: list[Author] = []
    used_ids: set[int] = set()
    for position, raw in enumerate(raw_authors):
        if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
            continue
        name = str(raw["name"]).strip()
        orcid = _normalize_orcid(raw.get("orcid"))
        source_author_id = (
            str(raw.get("source_author_id")).strip() if raw.get("source_author_id") else None
        )
        affiliations = [
            str(item).strip() for item in raw.get("affiliations", []) if str(item).strip()
        ]
        author: Author | None = None
        if orcid:
            author = session.scalar(select(Author).where(Author.orcid == orcid))
        elif source and source_author_id:
            source_identity = session.scalar(
                select(AuthorSourceRecord).where(
                    AuthorSourceRecord.source == source,
                    AuthorSourceRecord.source_author_id == source_author_id,
                )
            )
            if source_identity is not None:
                author = session.get(Author, source_identity.author_id)
        else:
            old_link = existing_links.get(position)
            if old_link is not None:
                candidate = session.get(Author, old_link.author_id)
                if candidate is not None and candidate.normalized_name == _normalize_name(name):
                    author = candidate

        provenance_item: dict[str, Any] = {
            "paper_id": paper.id,
            "position": position,
            "source": source or "paper_metadata",
            "source_record_id": source_row.source_id if source_row is not None else None,
            "source_url": source_row.source_url if source_row is not None else None,
            "raw_hash": source_row.raw_hash if source_row is not None else None,
        }
        if author is None:
            author = Author(
                canonical_name=name,
                normalized_name=_normalize_name(name),
                orcid=orcid,
                affiliations_json=json.dumps(affiliations, ensure_ascii=False),
                identity_status="resolved"
                if (orcid or (source and source_author_id))
                else "unresolved",
                provenance_json=json.dumps([provenance_item], ensure_ascii=False),
            )
            if source == "openalex" and source_author_id:
                author.openalex_id = source_author_id
            elif source == "semantic_scholar" and source_author_id:
                author.semantic_scholar_id = source_author_id
            session.add(author)
            session.flush()
        else:
            current_affiliations = json.loads(author.affiliations_json or "[]")
            author.affiliations_json = json.dumps(
                list(dict.fromkeys(current_affiliations + affiliations)), ensure_ascii=False
            )
            provenance = json.loads(author.provenance_json or "[]")
            if provenance_item not in provenance:
                provenance.append(provenance_item)
                author.provenance_json = json.dumps(provenance, ensure_ascii=False)

        if source and source_author_id:
            record = session.scalar(
                select(AuthorSourceRecord).where(
                    AuthorSourceRecord.source == source,
                    AuthorSourceRecord.source_author_id == source_author_id,
                )
            )
            if record is None:
                session.add(
                    AuthorSourceRecord(
                        author_id=author.id,
                        source=source,
                        source_author_id=source_author_id,
                        source_url=source_row.source_url if source_row is not None else None,
                        raw_hash=source_row.raw_hash if source_row is not None else None,
                        payload_json=json.dumps(raw, ensure_ascii=False),
                    )
                )

        link = existing_links.get(position)
        if link is None:
            session.add(
                PaperAuthorLink(
                    paper_id=paper.id,
                    author_id=author.id,
                    position=position,
                    credit_roles_json="[]",
                )
            )
        else:
            link.author_id = author.id
        used_ids.add(author.id)
        result.append(author)

    for position, link in existing_links.items():
        if position >= len(raw_authors):
            session.delete(link)
    session.flush()
    return result
