"""Field-level validation and additive merge for optional LLM analysis."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from research_navigator.analysis.providers import CitationValidationError
from research_navigator.analysis.structured import (
    CitationLocator,
    EvidenceLevel,
    PaperAnalysisOutput,
    QuickInterpretationZh,
)

_FULLTEXT_ONLY_FIELDS = {
    "theoretical_contribution",
    "baselines",
    "experimental_protocol",
    "major_results",
    "future_work_explicit",
    "limitations_author_stated",
}
_LIST_FIELDS = {
    "theoretical_contribution",
    "method_innovation",
    "research_route",
    "inputs",
    "outputs",
    "core_methods",
    "new_modules",
    "datasets",
    "baselines",
    "metrics",
    "experimental_protocol",
    "major_results",
    "claimed_contributions",
    "future_work_explicit",
    "limitations_author_stated",
}
_STRING_FIELDS = {"executive_summary", "research_background", "research_problem"}
_ALLOWED_FIELDS = _LIST_FIELDS | _STRING_FIELDS
_FULLTEXT_LEVELS = {
    "open_fulltext",
    "user_uploaded_fulltext",
    "publisher_authorized_fulltext",
}


def _nonempty(value: object) -> bool:
    return value not in (None, "", [], {})


def validate_and_merge_llm_analysis(
    deterministic: PaperAnalysisOutput,
    llm_output: Mapping[str, Any],
    *,
    accessible_snippets: Sequence[Mapping[str, Any]],
    evidence_level: EvidenceLevel,
) -> PaperAnalysisOutput:
    """Merge only cited, evidence-level-permitted, previously missing fields."""

    allowed_chunks = {snippet.get("chunk_id") for snippet in accessible_snippets}
    citation_by_chunk: dict[object, CitationLocator] = {}
    for snippet in accessible_snippets:
        raw = snippet.get("citation")
        if isinstance(raw, CitationLocator):
            citation = raw
        elif isinstance(raw, Mapping):
            citation = CitationLocator.model_validate(dict(raw))
        else:
            citation = CitationLocator(
                source_type="evidence", chunk_id=snippet.get("chunk_id")
            )
        citation_by_chunk[snippet.get("chunk_id")] = citation

    raw_citations = llm_output.get("citations", [])
    if not isinstance(raw_citations, list):
        raise CitationValidationError("citations must be a list")
    cited: dict[str, list[CitationLocator]] = {}
    for raw in raw_citations:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("field"), str):
            raise CitationValidationError("each citation needs a field")
        field = str(raw["field"])
        chunk_id = raw.get("chunk_id")
        if chunk_id not in allowed_chunks:
            raise CitationValidationError(f"citation chunk {chunk_id!r} was not supplied")
        locator = citation_by_chunk.get(chunk_id)
        if locator is None:
            raise CitationValidationError(f"citation chunk {chunk_id!r} has no locator")
        cited.setdefault(field, []).append(locator)

    updates: dict[str, object] = {}
    raw_quick = llm_output.get("quick_interpretation_zh")
    if isinstance(raw_quick, Mapping):
        quick_values = {
            key: value
            for key, value in raw_quick.items()
            if key in {"overview", "background", "problem", "task", "method", "result"}
            and (value is None or isinstance(value, str))
        }
        if quick_values and any(value for value in quick_values.values()):
            updates["quick_interpretation_zh"] = QuickInterpretationZh.model_validate(quick_values)
    field_states = dict(deterministic.field_states)
    field_citations = {key: list(value) for key, value in deterministic.field_citations.items()}
    missing = set(deterministic.missing_fields)
    for field in sorted(_ALLOWED_FIELDS):
        value = llm_output.get(field)
        if not _nonempty(value):
            continue
        if field not in cited:
            raise CitationValidationError(f"field {field!r} has no supported citation")
        if evidence_level not in _FULLTEXT_LEVELS and field in _FULLTEXT_ONLY_FIELDS:
            raise CitationValidationError(
                f"field {field!r} requires accessible full-text evidence"
            )
        if field in _LIST_FIELDS and not (
            isinstance(value, list) and all(isinstance(item, str) for item in value)
        ):
            raise CitationValidationError(f"field {field!r} must be a list of strings")
        if field in _STRING_FIELDS and not isinstance(value, str):
            raise CitationValidationError(f"field {field!r} must be a string")

        # The deterministic extractor remains authoritative. LLM output is
        # additive and never overwrites an already evidenced field.
        if deterministic.field_states.get(field) == "evidenced":
            continue
        updates[field] = value
        field_states[field] = "evidenced"
        field_citations[field] = cited[field]
        missing.discard(field)

    # Keep backward-compatible aliases synchronized when their rich field is added.
    if "executive_summary" in updates and deterministic.field_states.get("summary") != "evidenced":
        updates["summary"] = updates["executive_summary"]
    if "core_methods" in updates:
        updates["methods"] = updates["core_methods"]
    if "experimental_protocol" in updates:
        updates["experiment_design"] = updates["experimental_protocol"]
    if "major_results" in updates:
        updates["main_findings"] = updates["major_results"]
    if "claimed_contributions" in updates:
        updates["contributions"] = updates["claimed_contributions"]

    updates["field_states"] = field_states
    updates["field_citations"] = field_citations
    updates["missing_fields"] = sorted(missing)
    updates["warnings"] = list(deterministic.warnings) + [
        "Optional LLM enrichment was citation-validated and applied only to missing fields."
    ]
    return deterministic.model_copy(update=updates)
