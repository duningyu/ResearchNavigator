"""Deterministic search-mode classification and evidence-auditable discovery ranking."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from research_navigator.scholarly.base import PaperRecord

RANKING_RULE_VERSION = "discovery-ranking-v1"
_SEARCH_MODE_VERSION = "search-mode-v1"
_TOKEN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", re.IGNORECASE)
_DOI = re.compile(r"(?:doi:\s*)?10\.\d{4,9}/\S+", re.IGNORECASE)
_ARXIV = re.compile(r"(?:arxiv:\s*)?(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})", re.IGNORECASE)
_EXPLICIT_PREFIX = re.compile(r"\b(?:author|venue|dataset|doi|arxiv):", re.IGNORECASE)
_BOOLEAN = re.compile(r"\b(?:AND|OR|NOT)\b")


@dataclass(slots=True)
class RankedRecord:
    record: PaperRecord
    label: str
    relevance: float
    rank_score: float
    relevance_band: int


@dataclass(slots=True)
class DiscoveryComposition:
    requested_limit: int
    classic_target: int
    frontier_target: int
    classic_count: int
    frontier_count: int
    fill_count: int
    classic_shortfall: int
    frontier_shortfall: int
    candidate_pool_count: int
    rule_version: str = RANKING_RULE_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "requested_limit": self.requested_limit,
            "classic_target": self.classic_target,
            "frontier_target": self.frontier_target,
            "classic_count": self.classic_count,
            "frontier_count": self.frontier_count,
            "fill_count": self.fill_count,
            "classic_shortfall": self.classic_shortfall,
            "frontier_shortfall": self.frontier_shortfall,
            "candidate_pool_count": self.candidate_pool_count,
            "rule_version": self.rule_version,
        }


def classify_search_mode(query: str, requested_mode: str) -> str:
    """Classify broad 1-2 concept queries as discovery unless explicitly overridden."""

    if requested_mode not in {"auto", "precise", "discovery"}:
        raise ValueError(f"Unsupported search mode: {requested_mode}")
    if requested_mode != "auto":
        return requested_mode
    value = query.strip()
    if (
        (len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"})
        or _DOI.search(value)
        or _ARXIV.search(value)
        or _EXPLICIT_PREFIX.search(value)
        or _BOOLEAN.search(value)
    ):
        return "precise"
    tokens = [token.lower() for token in _TOKEN.findall(value)]
    return "discovery" if 1 <= len(tokens) <= 2 else "precise"


def search_mode_rule_version() -> str:
    return _SEARCH_MODE_VERSION


def _query_tokens(query: str) -> set[str]:
    return {token.lower() for token in _TOKEN.findall(query) if token.strip()}


def _record_text(record: PaperRecord) -> str:
    return " ".join(
        [
            record.title,
            record.abstract or "",
            " ".join(record.keywords),
            " ".join(record.concepts),
            " ".join(record.fields_of_study),
        ]
    ).lower()


def relevance_score(record: PaperRecord, query: str) -> float:
    tokens = _query_tokens(query)
    text = _record_text(record)
    lexical = 0.0 if not tokens else sum(1 for token in tokens if token in text) / len(tokens)
    source = max(0.0, float(record.source_score or 0.0))
    # Source adapters often emit small lexical/API scores. Keep them as the dominant ranking signal
    # when they clearly discriminate records while retaining a query-text floor for offline records.
    return max(source, lexical)


def _identity(record: PaperRecord) -> str:
    if record.doi:
        return f"doi:{record.doi.lower()}"
    if record.arxiv_id:
        return f"arxiv:{record.arxiv_id.lower()}"
    if record.external_ids:
        key, value = sorted(record.external_ids.items())[0]
        return f"{key}:{value}"
    return f"title:{record.title.lower()}:{record.publication_year or ''}"


def _seed_order(seed: str, record: PaperRecord) -> str:
    return hashlib.sha256(f"{seed}|{_identity(record)}".encode()).hexdigest()


def _band(relevance: float) -> int:
    # Rotation is allowed only inside a narrow relevance band. A 10.0 record can never be
    # displaced by a 0.01 record merely because the diversity seed changed.
    return int(math.floor(relevance * 100))


def _classic_eligible(record: PaperRecord, relevance: float) -> bool:
    if record.publication_year is None or record.citation_count is None:
        return False
    age = max(0, datetime.now(UTC).year - record.publication_year)
    return relevance >= 0.5 and age >= 5 and record.citation_count >= 50


def _frontier_eligible(record: PaperRecord, relevance: float) -> bool:
    if relevance <= 0:
        return False
    if record.publication_year is None:
        return True
    return record.publication_year >= datetime.now(UTC).year - 5


def _sorted(
    items: list[tuple[PaperRecord, float]], *, seed: str, classic: bool
) -> list[tuple[PaperRecord, float]]:
    def score(row: tuple[PaperRecord, float]) -> tuple[int, float, str]:
        record, relevance = row
        citations = float(record.citation_count or 0)
        year = float(record.publication_year or 0)
        secondary = math.log1p(citations) if classic else year / 10_000
        return (-_band(relevance), -secondary, _seed_order(seed, record))

    return sorted(items, key=score)


def rank_discovery(
    records: list[PaperRecord], *, query: str, limit: int, seed: str
) -> tuple[list[RankedRecord], DiscoveryComposition]:
    requested = max(1, limit)
    classic_target = round(requested * 0.2)
    frontier_target = requested - classic_target
    scored = [(record, relevance_score(record, query)) for record in records]
    scored = [row for row in scored if row[1] > 0]

    classics = _sorted(
        [row for row in scored if _classic_eligible(row[0], row[1])],
        seed=f"{seed}:classic",
        classic=True,
    )
    selected_classic = classics[:classic_target]
    used = {_identity(record) for record, _ in selected_classic}

    frontiers = _sorted(
        [
            row
            for row in scored
            if _identity(row[0]) not in used and _frontier_eligible(row[0], row[1])
        ],
        seed=f"{seed}:frontier",
        classic=False,
    )
    selected_frontier = frontiers[:frontier_target]
    used.update(_identity(record) for record, _ in selected_frontier)

    remaining_slots = requested - len(selected_classic) - len(selected_frontier)
    fill = _sorted(
        [row for row in scored if _identity(row[0]) not in used],
        seed=f"{seed}:fill",
        classic=False,
    )[:remaining_slots]

    ranked: list[RankedRecord] = []
    for label, rows in (
        ("classic_candidate", selected_classic),
        ("frontier_candidate", selected_frontier),
        ("relevance_fill", fill),
    ):
        for record, relevance in rows:
            ranked.append(
                RankedRecord(
                    record=record,
                    label=label,
                    relevance=round(relevance, 6),
                    rank_score=round(relevance, 6),
                    relevance_band=_band(relevance),
                )
            )

    composition = DiscoveryComposition(
        requested_limit=requested,
        classic_target=classic_target,
        frontier_target=frontier_target,
        classic_count=len(selected_classic),
        frontier_count=len(selected_frontier),
        fill_count=len(fill),
        classic_shortfall=max(0, classic_target - len(selected_classic)),
        frontier_shortfall=max(0, frontier_target - len(selected_frontier)),
        candidate_pool_count=len(scored),
    )
    return ranked[:requested], composition
