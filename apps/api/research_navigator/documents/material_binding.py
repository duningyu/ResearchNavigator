"""Conservative, versioned material binding; not a cryptographic authenticity claim.

Only an explicit first-page arXiv identifier can currently be corroborated against
an explicitly versioned record. DOI-only/publisher material remains unconfirmed:
neither a matching title nor a DOI in a bibliography establishes its version.
"""

from __future__ import annotations

import json
import re

from research_navigator.documents.parser import ParsedDocument
from research_navigator.models import Paper

BINDING_VERSION = "material-binding-v1"


def expected_arxiv_identity(paper: Paper) -> str | None:
    """Use an explicit version, never infer latest from a versionless dedup key."""
    try:
        ids = json.loads(paper.external_ids_json or "{}")
    except (ValueError, TypeError):
        return paper.arxiv_id
    if isinstance(ids, dict) and ids.get("arxiv_version_conflict"):
        return None
    if re.search(r"v\d+$", paper.arxiv_id or ""):
        return paper.arxiv_id
    versioned = ids.get("arxiv_versioned_id") if isinstance(ids, dict) else None
    if isinstance(versioned, str) and re.sub(r"v\d+$", "", versioned) == paper.arxiv_id:
        return versioned
    return paper.arxiv_id


def bind_material(
    *,
    paper_id: int,
    arxiv_id: str | None,
    doi: str | None,
    sha256: str,
    parsed: ParsedDocument,
) -> dict[str, object]:
    front = parsed.pages[0].text if parsed.pages else ""
    front = re.split(r"(?im)^\s*(?:references|bibliography)\s*$", front)[0]
    identifiers = set(
        re.findall(
            r"(?im)^\s*arxiv\s*:\s*((?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})v\d+)\b",
            front,
        )
    )
    expected = (arxiv_id or "").casefold().removeprefix("https://arxiv.org/abs/")
    actual = next(iter(identifiers)).casefold() if len(identifiers) == 1 else None
    state = "identity_unconfirmed"
    if actual and expected:
        if re.sub(r"v\d+$", "", actual) != re.sub(r"v\d+$", "", expected):
            state = "identity_mismatch"
        elif not re.search(r"v\d+$", expected):
            state = "version_unconfirmed"
        elif actual != expected:
            state = "version_mismatch"
        else:
            state = "verified"
    return {
        "binding_version": BINDING_VERSION,
        "paper_id": paper_id,
        "expected_arxiv_id": arxiv_id,
        "expected_doi": doi,
        "actual_version": actual,
        "status": state,
        "basis": "first_page_explicit_arxiv_identifier" if actual else "unconfirmed",
        "sha256": sha256,
        "parser_version": "pypdf-page-v1",
        "page_index_base": 0,
        "display_page_base": 1,
        "publication_completeness": "unconfirmed",
    }


def material_is_current(
    raw: str | None, *, paper_id: int, arxiv_id: str | None, doi: str | None, sha256: str
) -> bool:
    try:
        data = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return False
    return isinstance(data, dict) and all(
        (
            data.get("binding_version") == BINDING_VERSION,
            data.get("status") == "verified",
            data.get("paper_id") == paper_id,
            data.get("expected_arxiv_id") == arxiv_id,
            data.get("expected_doi") == doi,
            data.get("sha256") == sha256,
        )
    )
