"""Author card endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.authors.service import refresh_author_cards
from research_navigator.deps import get_current_user, get_db
from research_navigator.models import Author, Paper, PaperAuthorLink, User
from research_navigator.schemas.authors import AuthorCardRead

router = APIRouter(tags=["authors"])


def _read(author: Author, link: PaperAuthorLink | None = None) -> AuthorCardRead:
    return AuthorCardRead(
        id=author.id,
        canonical_name=author.canonical_name,
        orcid=author.orcid,
        openalex_id=author.openalex_id,
        semantic_scholar_id=author.semantic_scholar_id,
        affiliations=json.loads(author.affiliations_json),
        topics=json.loads(author.topics_json),
        works_count=author.works_count,
        citation_count=author.citation_count,
        homepage=author.homepage,
        identity_status=author.identity_status,
        provenance=json.loads(author.provenance_json),
        position=link.position if link is not None else None,
        credit_roles=json.loads(link.credit_roles_json) if link is not None else [],
    )


@router.post("/papers/{paper_id}/authors/refresh", response_model=list[AuthorCardRead])
def refresh_paper_authors(
    paper_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[AuthorCardRead]:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    refresh_author_cards(session, paper)
    session.commit()
    return list_paper_authors(paper_id, _, session)


@router.get("/papers/{paper_id}/authors", response_model=list[AuthorCardRead])
def list_paper_authors(
    paper_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[AuthorCardRead]:
    if session.get(Paper, paper_id) is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    links = list(
        session.scalars(
            select(PaperAuthorLink)
            .where(PaperAuthorLink.paper_id == paper_id)
            .order_by(PaperAuthorLink.position)
        )
    )
    return [
        _read(author, link)
        for link in links
        if (author := session.get(Author, link.author_id)) is not None
    ]


@router.get("/authors/{author_id}", response_model=AuthorCardRead)
def get_author(
    author_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> AuthorCardRead:
    author = session.get(Author, author_id)
    if author is None:
        raise HTTPException(status_code=404, detail="Author not found")
    return _read(author)
