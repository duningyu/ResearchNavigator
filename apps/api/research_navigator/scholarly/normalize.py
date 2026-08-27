"""Identifier normalization and conservative record deduplication."""

from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict

from research_navigator.scholarly.base import PaperAuthor, PaperRecord, SourceProvenance

_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_ARXIV_PREFIX = re.compile(r"^(?:https?://arxiv\.org/(?:abs|pdf)/|arxiv:\s*)", re.IGNORECASE)
_ARXIV_VERSION = re.compile(r"v\d+$", re.IGNORECASE)
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _DOI_PREFIX.sub("", value.strip()).strip().rstrip("./").lower()
    return normalized or None


def normalize_arxiv_id(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _ARXIV_PREFIX.sub("", value.strip()).strip()
    normalized = normalized.removesuffix(".pdf")
    normalized = _ARXIV_VERSION.sub("", normalized)
    return normalized or None


def normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    normalized = normalized.replace("—", " ").replace("–", "-")
    normalized = _NON_WORD.sub(" ", normalized)
    return _WHITESPACE.sub(" ", normalized).strip()


def normalize_record(record: PaperRecord) -> PaperRecord:
    abstract_provenance = record.abstract_provenance
    if record.abstract and abstract_provenance is None and len(record.source_provenance) == 1:
        abstract_provenance = record.source_provenance[0]
    return record.model_copy(
        update={
            "doi": normalize_doi(record.doi),
            "arxiv_id": normalize_arxiv_id(record.arxiv_id),
            "normalized_title": normalize_title(record.title),
            "source_urls": list(OrderedDict.fromkeys(record.source_urls)),
            "abstract_provenance": abstract_provenance,
        }
    )


def _dedup_key(record: PaperRecord) -> tuple[str, ...]:
    if record.doi:
        return ("doi", record.doi)
    if record.arxiv_id:
        return ("arxiv", record.arxiv_id)
    first_author = normalize_title(record.authors[0].name) if record.authors else ""
    return (
        "title",
        record.normalized_title or normalize_title(record.title),
        str(record.publication_year or ""),
        first_author,
    )


def _merge_authors(left: list[PaperAuthor], right: list[PaperAuthor]) -> list[PaperAuthor]:
    if not left:
        return right
    if not right:
        return left
    output: list[PaperAuthor] = []
    by_name = {normalize_title(author.name): author for author in left}
    for author in right:
        key = normalize_title(author.name)
        existing = by_name.get(key)
        if existing is None:
            by_name[key] = author
        elif not existing.orcid and author.orcid:
            by_name[key] = existing.model_copy(
                update={
                    "orcid": author.orcid,
                    "affiliations": list(
                        OrderedDict.fromkeys(existing.affiliations + author.affiliations)
                    ),
                    "source_author_id": existing.source_author_id or author.source_author_id,
                }
            )
    for key in [normalize_title(author.name) for author in left]:
        output.append(by_name.pop(key))
    output.extend(by_name.values())
    return output


def _merge_provenance(
    left: list[SourceProvenance], right: list[SourceProvenance]
) -> list[SourceProvenance]:
    merged: OrderedDict[tuple[str, str], SourceProvenance] = OrderedDict()
    for item in left + right:
        merged[(item.source, item.source_id)] = item
    return list(merged.values())


def merge_records(left: PaperRecord, right: PaperRecord) -> PaperRecord:
    left = normalize_record(left)
    right = normalize_record(right)
    abstract_candidates = [item for item in (left.abstract, right.abstract) if item]
    abstract = max(abstract_candidates, key=len) if abstract_candidates else None
    abstract_provenance = (
        left.abstract_provenance if abstract == left.abstract else right.abstract_provenance
    )
    return left.model_copy(
        update={
            "title": left.title if len(left.title) >= len(right.title) else right.title,
            "normalized_title": left.normalized_title or right.normalized_title,
            "translated_title": left.translated_title or right.translated_title,
            "abstract": abstract,
            "abstract_provenance": abstract_provenance,
            "publication_year": left.publication_year or right.publication_year,
            "publication_date": left.publication_date or right.publication_date,
            "authors": _merge_authors(left.authors, right.authors),
            "venue": left.venue or right.venue,
            "venue_type": left.venue_type or right.venue_type,
            "doi": left.doi or right.doi,
            "arxiv_id": left.arxiv_id or right.arxiv_id,
            "external_ids": {**right.external_ids, **left.external_ids},
            "source_urls": list(OrderedDict.fromkeys(left.source_urls + right.source_urls)),
            "publisher_url": left.publisher_url or right.publisher_url,
            "pdf_url": left.pdf_url or right.pdf_url,
            "open_access_status": left.open_access_status or right.open_access_status,
            "citation_count": max(
                [item for item in (left.citation_count, right.citation_count) if item is not None],
                default=None,
            ),
            "reference_count": max(
                [
                    item
                    for item in (left.reference_count, right.reference_count)
                    if item is not None
                ],
                default=None,
            ),
            "fields_of_study": list(
                OrderedDict.fromkeys(left.fields_of_study + right.fields_of_study)
            ),
            "concepts": list(OrderedDict.fromkeys(left.concepts + right.concepts)),
            "keywords": list(OrderedDict.fromkeys(left.keywords + right.keywords)),
            "source_provenance": _merge_provenance(left.source_provenance, right.source_provenance),
            "source_score": max(
                [item for item in (left.source_score, right.source_score) if item is not None],
                default=None,
            ),
        }
    )


def deduplicate_records(records: list[PaperRecord]) -> list[PaperRecord]:
    merged: OrderedDict[tuple[str, ...], PaperRecord] = OrderedDict()
    for raw in records:
        record = normalize_record(raw)
        key = _dedup_key(record)
        merged[key] = record if key not in merged else merge_records(merged[key], record)
    return list(merged.values())
