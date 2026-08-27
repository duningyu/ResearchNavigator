"""Explicitly marked offline fixture adapter for demos and tests."""

from __future__ import annotations

from research_navigator.scholarly.base import (
    AdapterSearchResult,
    PaperAuthor,
    PaperRecord,
    ScholarlyAdapter,
    SearchRequest,
    SourceProvenance,
    SourceStatus,
)

_FIXTURE_PAPERS = [
    PaperRecord(
        title="Anomaly Transformer for Multivariate Time Series Anomaly Detection",
        abstract=(
            "This fixture record describes transformer-based representation learning for "
            "multivariate time-series anomaly detection. It is bundled only for offline UI testing."
        ),
        publication_year=2022,
        authors=[PaperAuthor(name="Fixture Author A")],
        venue="Fixture Conference",
        external_ids={"fixture": "fixture-anomaly-transformer"},
        source_urls=["https://example.org/fixture/anomaly-transformer"],
        keywords=["time series", "anomaly detection", "transformer"],
        source_provenance=[
            SourceProvenance(
                source="fixture",
                source_id="fixture-anomaly-transformer",
                source_url="https://example.org/fixture/anomaly-transformer",
                is_fixture=True,
            )
        ],
    ),
    PaperRecord(
        title="TranAD-style Deep Networks for Anomaly Detection in Multivariate Time Series",
        abstract=(
            "A fixture summary for testing multivariate time-series anomaly detection search, "
            "ranking, and evidence-boundary behavior."
        ),
        publication_year=2022,
        authors=[PaperAuthor(name="Fixture Author B")],
        venue="Fixture Journal",
        external_ids={"fixture": "fixture-tranad"},
        source_urls=["https://example.org/fixture/tranad"],
        keywords=["multivariate", "time series", "anomaly detection"],
        source_provenance=[
            SourceProvenance(
                source="fixture",
                source_id="fixture-tranad",
                source_url="https://example.org/fixture/tranad",
                is_fixture=True,
            )
        ],
    ),
    PaperRecord(
        title="Future-Window Risk Ranking for Industrial Time-Series Alerts",
        abstract=(
            "Synthetic fixture metadata for a historical-window to future-horizon risk "
            "ranking task "
            "under a fixed alert budget. This is not a real publication."
        ),
        publication_year=2026,
        authors=[PaperAuthor(name="Synthetic Fixture Team")],
        venue="Synthetic fixture only",
        external_ids={"fixture": "synthetic-future-window-ranking"},
        source_urls=["https://example.org/fixture/future-window-ranking"],
        keywords=["future horizon", "time series", "alert ranking", "anomaly prediction"],
        source_provenance=[
            SourceProvenance(
                source="fixture",
                source_id="synthetic-future-window-ranking",
                source_url="https://example.org/fixture/future-window-ranking",
                is_fixture=True,
            )
        ],
    ),
    PaperRecord(
        title="A Survey on Time-Series Anomaly Detection",
        abstract=(
            "Fixture survey metadata covering tasks, datasets, methods, and evaluation protocols "
            "for time-series anomaly detection."
        ),
        publication_year=2024,
        authors=[PaperAuthor(name="Fixture Survey Author")],
        venue="Fixture Survey Venue",
        external_ids={"fixture": "fixture-tsad-survey"},
        source_urls=["https://example.org/fixture/tsad-survey"],
        keywords=["survey", "time series", "anomaly detection"],
        source_provenance=[
            SourceProvenance(
                source="fixture",
                source_id="fixture-tsad-survey",
                source_url="https://example.org/fixture/tsad-survey",
                is_fixture=True,
            )
        ],
    ),
    PaperRecord(
        title="Patch-Based Transformers for Long-Term Time-Series Forecasting",
        abstract="Fixture metadata for a patch-based time-series forecasting architecture.",
        publication_year=2023,
        authors=[PaperAuthor(name="Fixture Forecast Author")],
        venue="Fixture Conference",
        external_ids={"fixture": "fixture-patch-forecasting"},
        source_urls=["https://example.org/fixture/patch-forecasting"],
        keywords=["time series", "forecasting", "patch transformer"],
        source_provenance=[
            SourceProvenance(
                source="fixture",
                source_id="fixture-patch-forecasting",
                source_url="https://example.org/fixture/patch-forecasting",
                is_fixture=True,
            )
        ],
    ),
]


class FixtureAdapter(ScholarlyAdapter):
    name = "fixture"

    async def search(self, request: SearchRequest) -> AdapterSearchResult:
        query_tokens = {token for token in request.query.lower().replace("-", " ").split() if token}
        scored: list[tuple[int, PaperRecord]] = []
        for paper in _FIXTURE_PAPERS:
            haystack = " ".join(
                [paper.title, paper.abstract or "", " ".join(paper.keywords)]
            ).lower()
            score = sum(1 for token in query_tokens if token in haystack)
            if not query_tokens or score > 0:
                scored.append((score, paper.model_copy(update={"source_score": float(score)})))
        records = [item[1] for item in sorted(scored, key=lambda item: item[0], reverse=True)]
        records = records[request.offset : request.offset + request.limit]
        return AdapterSearchResult(
            records=records,
            status=SourceStatus(status="ok", result_count=len(records), detail="offline fixture"),
        )
