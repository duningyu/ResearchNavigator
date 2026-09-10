"""Bounded, inspectable query terminology adaptation; not model translation.

Unknown Chinese terms remain intact. Never append a domain or replace original
bibliographic titles. The caller retains the user's original search session.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Literal, Protocol

_ENGLISH_INDEXES = frozenset({"arxiv", "openalex", "crossref", "semantic_scholar"})
_TERMS = {
    "未来窗口预警": "future window early warning",
    "图像语义分割": "image semantic segmentation",
    "语义分割": "semantic segmentation",
    "实例分割": "instance segmentation",
    "图像分类": "image classification",
    "目标检测": "object detection",
    "检索增强生成": "retrieval augmented generation",
    "多变量时间序列": "multivariate time series",
    "时间序列": "time series",
    "异常检测": "anomaly detection",
    "深度学习": "deep learning",
    "机器学习": "machine learning",
    "强化学习": "reinforcement learning",
    "自然语言处理": "natural language processing",
    "图神经网络": "graph neural network",
    "不确定性估计": "uncertainty estimation",
    "域适应": "domain adaptation",
    "迁移学习": "transfer learning",
}
_CJK = re.compile(r"[\u3400-\u9fff]")
_EXACT_OR_SYNTAX = re.compile(r'["“”]|\b10\.\d{4,9}/|\b\w+:|\b(?:AND|OR|NOT)\b')

QueryAdaptationStatus = Literal["NOT_REQUIRED", "ADAPTED", "FALLBACK_ORIGINAL"]


@dataclass(frozen=True, slots=True)
class QueryAdaptationResult:
    """The bounded, user-safe outcome of adapting one source query."""

    original_query: str
    adapted_query: str | None
    status: QueryAdaptationStatus
    source: str
    used_fallback: bool
    failure_reason: str | None = None

    @property
    def executed_queries(self) -> tuple[str, ...]:
        if self.status == "ADAPTED" and self.adapted_query:
            return (self.original_query, self.adapted_query)
        return (self.original_query,)

    @property
    def executed_query(self) -> str:
        return self.adapted_query or self.original_query


class QueryAdaptationProvider(Protocol):
    async def adapt(self, query: str, source: str) -> str | None:
        """Return a safe adapted query, or None when no safe result exists."""


class ControlledGlossaryQueryAdapter:
    """Async adapter boundary for the existing bounded glossary.

    This is deliberately not a general translation implementation.  It gives
    the search service an injectable failure/timeout boundary while preserving
    the current deterministic glossary as the default behavior.
    """

    mode = "controlled_glossary"

    async def adapt(self, query: str, source: str) -> str | None:
        adapted, status = adapt_query(query, source)
        if status != "controlled_glossary":
            return None
        return adapted


def is_precise_query(query: str) -> bool:
    """Return whether a query contains syntax that must not be expanded."""

    return bool(_EXACT_OR_SYNTAX.search(query))


def adapt_query(query: str, source: str) -> tuple[str, str]:
    if source not in _ENGLISH_INDEXES or not _CJK.search(query) or is_precise_query(query):
        return query, "original"
    adapted = query
    for term in sorted(_TERMS, key=len, reverse=True):
        adapted = adapted.replace(term, f" {_TERMS[term]} ")
    adapted = " ".join(adapted.split())
    if adapted == query:
        return query, "untranslated"
    if _CJK.search(adapted):
        return adapted, "partial_glossary"
    return adapted, "controlled_glossary"


def _fallback_result(
    query: str,
    provider: QueryAdaptationProvider,
    reason: str,
) -> QueryAdaptationResult:
    return QueryAdaptationResult(
        original_query=query,
        adapted_query=None,
        status="FALLBACK_ORIGINAL",
        source=getattr(provider, "mode", "provider"),
        used_fallback=True,
        failure_reason=reason,
    )


async def resolve_query_adaptation(
    query: str,
    source: str,
    provider: QueryAdaptationProvider,
    timeout_seconds: float,
) -> QueryAdaptationResult:
    """Resolve adaptation without ever making it a prerequisite for search."""

    if source not in _ENGLISH_INDEXES or not _CJK.search(query) or is_precise_query(query):
        return QueryAdaptationResult(
            original_query=query,
            adapted_query=None,
            status="NOT_REQUIRED",
            source="original",
            used_fallback=False,
        )

    try:
        candidate = await asyncio.wait_for(
            provider.adapt(query, source),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        return _fallback_result(query, provider, "timeout")
    except Exception:
        return _fallback_result(query, provider, "provider_error")

    if not isinstance(candidate, str) or not candidate.strip():
        return _fallback_result(query, provider, "empty_response")

    normalized = " ".join(candidate.split())
    if normalized == query or _CJK.search(normalized):
        return _fallback_result(query, provider, "partial_response")

    return QueryAdaptationResult(
        original_query=query,
        adapted_query=normalized,
        status="ADAPTED",
        source=getattr(provider, "mode", "provider"),
        used_fallback=False,
    )
