"""Deterministic dense hashing and hybrid result ranking."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def _tokens(text: str) -> list[str]:
    raw = [token.lower() for token in _TOKEN_RE.findall(text)]
    chinese = [token for token in raw if len(token) == 1 and "\u4e00" <= token <= "\u9fff"]
    bigrams = ["".join(chinese[index : index + 2]) for index in range(len(chinese) - 1)]
    return raw + bigrams


def hashing_vector(text: str, *, dimensions: int = 128) -> list[float]:
    vector = [0.0] * dimensions
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
        index = int.from_bytes(digest[:8], "big") % dimensions
        sign = 1.0 if digest[8] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Vector dimensions must match")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


@dataclass(frozen=True, slots=True)
class HybridCandidate:
    chunk_id: int
    text: str
    section: str
    page_start: int
    page_end: int
    lexical_score: float
    dense_score: float
    document_id: int | None = None
    evidence_level: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    chunk_id: int
    text: str
    section: str
    page_start: int
    page_end: int
    score: float
    lexical_score: float
    dense_score: float
    document_id: int | None
    evidence_level: str | None

    @property
    def citation(self) -> dict[str, int | str | None]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "section": self.section,
            "page_start": self.page_start,
            "page_end": self.page_end,
        }


def rank_hybrid(
    candidates: list[HybridCandidate],
    *,
    top_k: int,
    lexical_weight: float = 0.45,
    dense_weight: float = 0.55,
) -> list[RetrievalHit]:
    if top_k < 1:
        raise ValueError("top_k must be positive")
    ranked = [
        RetrievalHit(
            chunk_id=item.chunk_id,
            text=item.text,
            section=item.section,
            page_start=item.page_start,
            page_end=item.page_end,
            score=lexical_weight * max(0.0, item.lexical_score)
            + dense_weight * max(-1.0, item.dense_score),
            lexical_score=item.lexical_score,
            dense_score=item.dense_score,
            document_id=item.document_id,
            evidence_level=item.evidence_level,
        )
        for item in candidates
    ]
    return sorted(ranked, key=lambda item: item.score, reverse=True)[:top_k]
