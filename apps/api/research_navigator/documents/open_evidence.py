"""Explicit contracts for acquiring and caching public scholarly material."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

CachePolicy = Literal["shared_durable", "not_cacheable", "reject"]
OpenEvidenceSource = Literal["arxiv", "openalex"]
OpenEvidenceOutcome = Literal[
    "cache_hit_fulltext",
    "fulltext_acquired",
    "abstract_acquired",
    "no_open_fulltext",
    "rights_insufficient",
    "source_unavailable",
    "already_sufficient",
]


class OpenMaterialCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: OpenEvidenceSource
    source_record_id: str
    pdf_url: str
    license: str | None = None
    rights_basis: str
    cache_policy: CachePolicy


def as_open_evidence_source(source: str) -> OpenEvidenceSource | None:
    """Narrow adapter-provided source names at the public-material boundary."""
    if source == "arxiv":
        return "arxiv"
    if source == "openalex":
        return "openalex"
    return None


def expected_arxiv_identity(arxiv_id: str | None) -> str | None:
    """Return the exact record identity; versions are intentionally significant."""
    return arxiv_id.strip() if arxiv_id and arxiv_id.strip() else None


def _normalized_license(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower().rstrip("/")
    normalized = normalized.replace("https://", "").replace("http://", "")
    if "creativecommons.org/licenses/" in normalized:
        normalized = normalized.split("creativecommons.org/licenses/", 1)[1]
    return normalized.split("/", 1)[0]


def classify_cache_policy(*, source: str, license: str | None, rights_basis: str) -> CachePolicy:
    """Fail closed unless the source and an explicit approved license are known."""
    approved = {"cc0", "by", "cc-by", "by-sa", "cc-by-sa", "public-domain"}
    normalized = _normalized_license(license)
    if source == "arxiv" and rights_basis == "arxiv_license" and normalized in approved:
        return "shared_durable"
    if (
        source == "openalex"
        and rights_basis == "openalex_explicit_license"
        and normalized in approved
    ):
        return "shared_durable"
    return "not_cacheable" if license or rights_basis else "reject"
