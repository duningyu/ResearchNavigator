"""Persistence and hybrid retrieval for parsed paper chunks."""

from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from research_navigator.documents.parser import ParsedDocument, chunk_document
from research_navigator.documents.retrieval import (
    HybridCandidate,
    RetrievalHit,
    cosine_similarity,
    hashing_vector,
    rank_hybrid,
)
from research_navigator.models import PaperChunk, PaperDocument


def index_document(
    session: Session,
    *,
    document: PaperDocument,
    parsed: ParsedDocument,
) -> int:
    chunks = chunk_document(parsed)
    for chunk in chunks:
        vector = hashing_vector(chunk.text)
        row = PaperChunk(
            document_id=document.id,
            paper_id=document.paper_id,
            user_id=document.user_id,
            section=chunk.section,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            text_hash=hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
            vector_json=json.dumps(vector, separators=(",", ":")),
            source_type=document.source_type,
            evidence_level=document.evidence_level,
            ingestion_version=document.ingestion_version,
        )
        session.add(row)
        session.flush()
        if session.bind is not None and session.bind.dialect.name == "sqlite":
            session.execute(
                text(
                    "INSERT INTO paper_chunks_fts "
                    "(chunk_id, document_id, paper_id, user_id, section, text) "
                    "VALUES (:chunk_id, :document_id, :paper_id, :user_id, :section, :text)"
                ),
                {
                    "chunk_id": str(row.id),
                    "document_id": str(document.id),
                    "paper_id": str(document.paper_id),
                    "user_id": "" if document.user_id is None else str(document.user_id),
                    "section": row.section,
                    "text": row.text,
                },
            )
    return len(chunks)


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", query.lower())
    return " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens[:20])


def search_document_chunks(
    session: Session,
    *,
    user_id: int,
    paper_id: int,
    query: str,
    top_k: int,
) -> list[RetrievalHit]:
    accessible = list(
        session.scalars(
            select(PaperChunk).where(
                PaperChunk.paper_id == paper_id,
                or_(PaperChunk.user_id == user_id, PaperChunk.user_id.is_(None)),
            )
        )
    )
    if not accessible:
        return []
    lexical_by_id: dict[int, float] = {}
    fts_query = _fts_query(query)
    is_sqlite = session.bind is not None and session.bind.dialect.name == "sqlite"
    if fts_query and is_sqlite:
        rows = session.execute(
            text(
                "SELECT CAST(chunk_id AS INTEGER) AS chunk_id, bm25(paper_chunks_fts) AS rank "
                "FROM paper_chunks_fts WHERE paper_chunks_fts MATCH :query "
                "AND paper_id = :paper_id AND (user_id = :user_id OR user_id = '') "
                "LIMIT :limit"
            ),
            {
                "query": fts_query,
                "paper_id": str(paper_id),
                "user_id": str(user_id),
                "limit": max(20, top_k * 5),
            },
        )
        for chunk_id, rank in rows:
            lexical_by_id[int(chunk_id)] = 1.0 / (1.0 + abs(float(rank)))
    elif query.strip() and not is_sqlite:
        rows = session.execute(
            text(
                "SELECT id, ts_rank(to_tsvector('simple', coalesce(text, '')), "
                "websearch_to_tsquery('simple', :query)) AS rank "
                "FROM paper_chunks WHERE paper_id = :paper_id "
                "AND (user_id = :user_id OR user_id IS NULL) "
                "AND to_tsvector('simple', coalesce(text, '')) @@ "
                "websearch_to_tsquery('simple', :query) "
                "ORDER BY rank DESC, id ASC LIMIT :limit"
            ),
            {"query": query, "paper_id": paper_id, "user_id": user_id, "limit": max(20, top_k * 5)},
        )
        for chunk_id, rank in rows:
            lexical_by_id[int(chunk_id)] = float(rank)
    query_vector = hashing_vector(query)
    candidates = [
        HybridCandidate(
            chunk_id=row.id,
            document_id=row.document_id,
            text=row.text,
            section=row.section,
            page_start=row.page_start,
            page_end=row.page_end,
            lexical_score=lexical_by_id.get(row.id, 0.0),
            dense_score=cosine_similarity(query_vector, json.loads(row.vector_json)),
            evidence_level=row.evidence_level,
        )
        for row in accessible
    ]
    return rank_hybrid(candidates, top_k=top_k)
