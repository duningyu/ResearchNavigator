"""Conservative copyright and access policy for OA candidates."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from research_navigator.open_access.base import OpenAccessCandidate

_PERMISSIVE = {"cc0", "cc-by", "cc-by-sa", "public-domain"}
_LIMITED = {"cc-by-nc", "cc-by-nd", "cc-by-nc-sa", "cc-by-nc-nd"}


def normalize_license(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    normalized = normalized.replace("creativecommons.org/licenses/", "")
    normalized = normalized.replace("creativecommons.org/publicdomain/zero/", "cc0/")
    normalized = normalized.replace("https://", "").replace("http://", "")
    normalized = normalized.replace("legalcode", "")
    normalized = normalized.replace("_", "-").replace(" ", "-")
    normalized = normalized.replace("ccby", "cc-by")
    normalized = re.sub(r"[^a-z0-9-]+", "-", normalized).strip("-")
    normalized = re.sub(r"-(?:1|2|2-5|3|4)(?:-0)?$", "", normalized)
    normalized = normalized.replace("cc-by-nc-nd-", "cc-by-nc-nd")
    aliases = {
        "by": "cc-by",
        "by-sa": "cc-by-sa",
        "by-nc": "cc-by-nc",
        "by-nd": "cc-by-nd",
        "by-nc-sa": "cc-by-nc-sa",
        "by-nc-nd": "cc-by-nc-nd",
        "publicdomain": "public-domain",
        "public-domain-mark": "public-domain",
    }
    normalized = aliases.get(normalized, normalized)
    for known in sorted(_PERMISSIVE | _LIMITED, key=len, reverse=True):
        if normalized == known or normalized.startswith(f"{known}-"):
            return known
    if normalized in {"cc-0", "zero", "pdm"}:
        return "cc0"
    return normalized or None


def _unsafe_url_reason(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        return "unsupported_url_scheme"
    if parsed.username is not None or parsed.password is not None:
        return "url_contains_userinfo"
    if not parsed.hostname:
        return "url_missing_host"
    return None


def decide_access(candidate: OpenAccessCandidate) -> OpenAccessCandidate:
    normalized_license = normalize_license(candidate.license)
    reason = _unsafe_url_reason(candidate.pdf_url or candidate.landing_url)
    decision = candidate.access_decision
    if reason is not None:
        decision = "rejected"
    elif candidate.requires_auth:
        decision = "rejected"
        reason = "authentication_required"
    elif not candidate.is_oa:
        decision = "rejected"
        reason = "not_open_access"
    elif candidate.pdf_url is None:
        decision = "link_only"
        reason = "pdf_url_unavailable"
    elif normalized_license in _PERMISSIVE:
        decision = "auto_ingest"
        reason = None
    elif normalized_license in _LIMITED:
        decision = "requires_user_confirmation"
        reason = "limited_license_requires_confirmation"
    else:
        decision = "link_only"
        reason = "license_unknown"
    return candidate.model_copy(
        update={
            "normalized_license": normalized_license,
            "access_decision": decision,
            "rejection_reason": reason,
        }
    )
