"""Conservative structured extraction from legally accessible paper text."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

EvidenceLevel = Literal[
    "metadata_only",
    "abstract_only",
    "open_fulltext",
    "user_uploaded_fulltext",
    "publisher_authorized_fulltext",
]
FieldEvidenceState = Literal["evidenced", "insufficient_evidence", "unknown"]

_FULLTEXT_LEVELS = {
    "open_fulltext",
    "user_uploaded_fulltext",
    "publisher_authorized_fulltext",
}


class CitationLocator(BaseModel):
    source_type: str
    section: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    chunk_id: int | None = None
    supporting_text: str | None = None


class EvidenceSpan(BaseModel):
    """A legally accessible text span paired with its exact provenance locator."""

    text: str
    citation: CitationLocator


class TaskDefinition(BaseModel):
    input: str | None = None
    output: str | None = None
    setting: str | None = None


class PaperAnalysisOutput(BaseModel):
    paper_id: int
    evidence_level: EvidenceLevel
    analysis_version: str = "structured-v3"
    citation_granularity: Literal["sentence_to_chunk"] = "sentence_to_chunk"

    # Rich evidence-grade fields used by the ResearchNavigator UI.
    executive_summary: str
    research_background: str | None = None
    research_problem: str | None = None
    task_definition: TaskDefinition = Field(default_factory=TaskDefinition)
    theoretical_contribution: list[str] = Field(default_factory=list)
    method_innovation: list[str] = Field(default_factory=list)
    research_route: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    core_methods: list[str] = Field(default_factory=list)
    new_modules: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    baselines: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    experimental_protocol: list[str] = Field(default_factory=list)
    major_results: list[str] = Field(default_factory=list)
    claimed_contributions: list[str] = Field(default_factory=list)
    future_work_explicit: list[str] = Field(default_factory=list)
    limitations_author_stated: list[str] = Field(default_factory=list)
    limitations_inferred: list[str] = Field(default_factory=list)

    # Backward-compatible aliases retained for existing consumers.
    summary: str
    methods: list[str] = Field(default_factory=list)
    novelty_claims: list[str] = Field(default_factory=list)
    experiment_design: list[str] = Field(default_factory=list)
    main_findings: list[str] = Field(default_factory=list)
    contributions: list[str] = Field(default_factory=list)

    code_repositories: list[str] = Field(default_factory=list)
    data_links: list[str] = Field(default_factory=list)
    citations: list[CitationLocator] = Field(default_factory=list)
    field_states: dict[str, FieldEvidenceState] = Field(default_factory=dict)
    field_citations: dict[str, list[CitationLocator]] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def _first_matching(sentences: list[str], terms: tuple[str, ...]) -> str | None:
    for sentence in sentences:
        lower = sentence.lower()
        if any(term in lower for term in terms):
            return sentence
    return None


def _all_matching(sentences: list[str], terms: tuple[str, ...], *, limit: int = 3) -> list[str]:
    found: list[str] = []
    for sentence in sentences:
        lower = sentence.lower()
        if any(term in lower for term in terms):
            found.append(sentence)
        if len(found) >= limit:
            break
    return found


def _extract_methods(text: str) -> list[str]:
    patterns = [
        (r"\btransformer(?:s)?\b", "Transformer"),
        (r"\b(?:temporal convolutional network|tcn)\b", "Temporal Convolutional Network"),
        (r"\blstm\b", "LSTM"),
        (r"\bgru\b", "GRU"),
        (r"\bmamba\b", "Mamba"),
        (r"\bcontrastive learning\b", "Contrastive Learning"),
        (r"\bpairwise rank(?:ing)?\b", "Pairwise Ranking"),
        (r"\bautoencoder\b", "Autoencoder"),
        (r"\bretrieval[- ]augmented generation\b|\brag\b", "Retrieval-Augmented Generation"),
        (r"\bgraph neural network\b|\bgnn\b", "Graph Neural Network"),
        (r"\bconvolutional neural network\b|\bcnn\b", "Convolutional Neural Network"),
    ]
    return [label for pattern, label in patterns if re.search(pattern, text, re.IGNORECASE)]


def _extract_known_items(text: str, candidates: tuple[str, ...]) -> list[str]:
    lower = text.lower()
    return [name for name in candidates if name.lower() in lower]


def _extract_task_io(sentences: list[str]) -> tuple[list[str], list[str], TaskDefinition]:
    input_sentence = _first_matching(
        sentences,
        ("input", "given historical", "historical window", "time series", "multivariate"),
    )
    output_sentence = _first_matching(
        sentences,
        ("output", "predict", "forecast", "rank", "detect", "classification"),
    )
    inputs = [input_sentence] if input_sentence else []
    outputs = [output_sentence] if output_sentence else []
    return inputs, outputs, TaskDefinition(input=input_sentence, output=output_sentence)


def _citations_for(
    value: object,
    evidence_spans: list[EvidenceSpan],
) -> list[CitationLocator]:
    if value is None or value == "" or value == [] or value == {}:
        return []

    def claim_texts(item: object) -> list[str]:
        if isinstance(item, str):
            return _sentences(item) or ([item.strip()] if item.strip() else [])
        if isinstance(item, dict):
            return [text for nested in item.values() for text in claim_texts(nested)]
        if isinstance(item, (list, tuple, set)):
            return [text for nested in item for text in claim_texts(nested)]
        return []

    def comparable(item: str) -> str:
        return re.sub(r"[^\w]+", " ", item, flags=re.UNICODE).strip().casefold()

    aligned: list[CitationLocator] = []
    seen: set[tuple[str, str | None, int | None, int | None, int | None, str]] = set()
    for claim in claim_texts(value):
        normalized_claim = comparable(claim)
        if not normalized_claim:
            continue
        for span in evidence_spans:
            for sentence in _sentences(span.text) or [span.text.strip()]:
                normalized_sentence = comparable(sentence)
                if not normalized_sentence:
                    continue
                if (
                    normalized_claim not in normalized_sentence
                    and normalized_sentence not in normalized_claim
                ):
                    continue
                citation = span.citation.model_copy(update={"supporting_text": sentence})
                identity = (
                    citation.source_type,
                    citation.section,
                    citation.page_start,
                    citation.page_end,
                    citation.chunk_id,
                    sentence,
                )
                if identity not in seen:
                    seen.add(identity)
                    aligned.append(citation)
                break
    return aligned


def analyze_accessible_text(
    *,
    paper_id: int,
    text: str,
    evidence_level: EvidenceLevel,
    citations: Sequence[dict[str, object] | CitationLocator],
    evidence_spans: Sequence[dict[str, object] | EvidenceSpan] | None = None,
) -> PaperAnalysisOutput:
    """Extract only claims supported by the supplied accessibility level.

    The extractor is deterministic and deliberately conservative. Fields that require
    paper body evidence are marked ``insufficient_evidence`` for abstract/metadata-only
    inputs rather than being inferred from general knowledge or the paper title.
    """

    normalized_citations = [
        item if isinstance(item, CitationLocator) else CitationLocator.model_validate(item)
        for item in citations
    ]
    normalized_spans = [
        item if isinstance(item, EvidenceSpan) else EvidenceSpan.model_validate(item)
        for item in (evidence_spans or [])
    ]
    if not normalized_spans and len(normalized_citations) == 1:
        normalized_spans = [EvidenceSpan(text=text, citation=normalized_citations[0])]
    if not normalized_citations and normalized_spans:
        normalized_citations = [span.citation for span in normalized_spans]
    sentences = _sentences(text)
    executive_summary = " ".join(sentences[:2]) if sentences else "未在当前可访问文本中找到。"
    research_problem = _first_matching(
        sentences,
        ("we propose", "we study", "we investigate", "we address", "predict", "detect"),
    )
    background = _first_matching(
        sentences,
        ("challenge", "problem", "existing", "however", "motivat", "important"),
    )
    core_methods = _extract_methods(text)
    datasets = _extract_known_items(
        text,
        (
            "SWaT",
            "WADI",
            "SMAP",
            "MSL",
            "SMD",
            "Backblaze",
            "Scania",
            "3W",
            "MetroPT-3",
            "PRONTO",
            "CARE",
            "PreDist",
            "N-CMAPSS",
            "C-MAPSS",
        ),
    )
    metrics = _extract_known_items(
        text,
        (
            "PR-AUC",
            "ROC-AUC",
            "Precision",
            "Recall",
            "F1",
            "Brier",
            "ECE",
            "NDCG",
            "AUC",
            "Accuracy",
        ),
    )
    inputs, outputs, task_definition = _extract_task_io(sentences)

    contribution_sentences = _all_matching(
        sentences,
        ("we propose", "we introduce", "our contribution", "we present", "we develop"),
        limit=3,
    )
    method_innovation = [
        sentence
        for sentence in contribution_sentences
        if any(method.lower() in sentence.lower() for method in core_methods)
        or any(term in sentence.lower() for term in ("method", "framework", "model", "module"))
    ]
    theoretical_contribution = _all_matching(
        sentences,
        ("theorem", "theoretical", "proof", "proposition", "lemma"),
        limit=3,
    )
    research_route = _all_matching(
        sentences,
        ("pipeline", "workflow", "first ", "then ", "followed by", "consists of"),
        limit=3,
    )
    new_modules = _all_matching(
        sentences,
        ("new module", "novel module", "we introduce a module", "we propose a module", " block"),
        limit=3,
    )
    baselines = _all_matching(
        sentences,
        ("baseline", "compared with", "compare against", "outperform"),
        limit=3,
    )
    major_results = _all_matching(
        sentences,
        ("improve", "outperform", "result", "achieve", "increase", "decrease"),
        limit=3,
    )

    future: list[str] = []
    limitations: list[str] = []
    protocol: list[str] = []
    missing: list[str] = []
    warnings: list[str] = []

    restricted_fulltext_fields = {
        "experimental_protocol",
        "future_work_explicit",
        "limitations_author_stated",
    }

    if evidence_level in _FULLTEXT_LEVELS:
        future = _all_matching(
            sentences, ("future work", "in future work", "future research"), limit=3
        )
        limitations = _all_matching(
            sentences,
            ("limitation", "limited by", "a limitation", "we acknowledge"),
            limit=3,
        )
        protocol = _all_matching(
            sentences,
            (
                "experiment",
                "evaluate",
                "evaluation",
                "train split",
                "test split",
                "validation",
                "cross-validation",
            ),
            limit=4,
        )
        if not future:
            missing.append("future_work_explicit")
        if not limitations:
            missing.append("limitations_author_stated")
        if not protocol:
            missing.append("experimental_protocol")
    else:
        missing.extend(sorted(restricted_fulltext_fields))
        if evidence_level == "abstract_only":
            warnings.extend(
                [
                    "摘要级证据不足",
                    "当前为摘要级证据，不抽取正文中的 Future Work、作者局限、参数或实验协议细节。",
                ]
            )
        else:
            warnings.append("当前仅有元数据，结构化分析能力受限。")

    if not research_problem:
        missing.append("research_problem")
    if not core_methods:
        missing.append("core_methods")
    if not datasets:
        missing.append("datasets")

    task_definition_value = {
        key: value
        for key, value in task_definition.model_dump().items()
        if value not in (None, "", [], {})
    }
    values: dict[str, object] = {
        "executive_summary": executive_summary,
        "research_background": background,
        "research_problem": research_problem,
        "task_definition": task_definition_value,
        "theoretical_contribution": theoretical_contribution,
        "method_innovation": method_innovation,
        "research_route": research_route,
        "inputs": inputs,
        "outputs": outputs,
        "core_methods": core_methods,
        "new_modules": new_modules,
        "datasets": datasets,
        "baselines": baselines,
        "metrics": metrics,
        "experimental_protocol": protocol,
        "major_results": major_results,
        "claimed_contributions": contribution_sentences,
        "future_work_explicit": future,
        "limitations_author_stated": limitations,
        "limitations_inferred": [],
    }
    field_states: dict[str, FieldEvidenceState] = {}
    field_citations: dict[str, list[CitationLocator]] = {}
    for field_name, value in values.items():
        if evidence_level not in _FULLTEXT_LEVELS and field_name in restricted_fulltext_fields:
            field_states[field_name] = "insufficient_evidence"
            field_citations[field_name] = []
        elif value is None or value == "" or value == [] or value == {}:
            field_states[field_name] = "unknown"
            field_citations[field_name] = []
        else:
            field_states[field_name] = "evidenced"
            field_citations[field_name] = _citations_for(value, normalized_spans)

    return PaperAnalysisOutput(
        paper_id=paper_id,
        evidence_level=evidence_level,
        executive_summary=executive_summary,
        summary=executive_summary,
        research_background=background,
        research_problem=research_problem,
        task_definition=task_definition,
        theoretical_contribution=theoretical_contribution,
        method_innovation=method_innovation,
        research_route=research_route,
        inputs=inputs,
        outputs=outputs,
        core_methods=core_methods,
        methods=core_methods,
        new_modules=new_modules,
        novelty_claims=contribution_sentences,
        datasets=datasets,
        baselines=baselines,
        metrics=metrics,
        experimental_protocol=protocol,
        experiment_design=protocol,
        major_results=major_results,
        main_findings=major_results,
        claimed_contributions=contribution_sentences,
        contributions=contribution_sentences,
        future_work_explicit=future,
        limitations_author_stated=limitations,
        limitations_inferred=[],
        citations=normalized_citations,
        field_states=field_states,
        field_citations=field_citations,
        missing_fields=sorted(set(missing)),
        warnings=warnings,
    )
