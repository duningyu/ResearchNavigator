from research_navigator.scholarly.base import PaperRecord
from research_navigator.scholarly.ranking import classify_search_mode, rank_discovery


def _record(index: int, *, classic: bool, relevance: float = 1.0) -> PaperRecord:
    year = 2015 if classic else 2026
    citations = 500 + index if classic else 5 + index
    return PaperRecord(
        title=f"Attention mechanism anomaly detection paper {index}",
        abstract="attention anomaly detection time series research",
        publication_year=year,
        citation_count=citations,
        keywords=["attention", "anomaly detection"],
        external_ids={"fixture": f"paper-{index}"},
        source_score=relevance,
    )


def test_auto_mode_classifies_broad_and_precise_queries() -> None:
    cases = {
        "attention": "discovery",
        "anomaly detection": "discovery",
        "时序异常": "discovery",
        '"Attention Is All You Need"': "precise",
        "10.48550/arXiv.1706.03762": "precise",
        "arXiv:1706.03762": "precise",
        "attention AND transformer AND time series": "precise",
        "author:Vaswani attention": "precise",
    }
    for query, expected in cases.items():
        assert classify_search_mode(query, "auto") == expected
    assert classify_search_mode("attention", "precise") == "precise"
    assert classify_search_mode("long explicit title", "discovery") == "discovery"


def test_discovery_top50_targets_ten_classic_and_forty_frontier() -> None:
    records = [_record(index, classic=index < 20) for index in range(80)]
    ranked, composition = rank_discovery(records, query="attention", limit=50, seed="seed-a")

    assert len(ranked) == 50
    labels = [item.label for item in ranked]
    assert labels.count("classic_candidate") == 10
    assert labels.count("frontier_candidate") == 40
    assert composition.classic_target == 10
    assert composition.frontier_target == 40
    assert composition.classic_shortfall == 0
    assert composition.frontier_shortfall == 0


def test_discovery_seed_is_deterministic_and_only_rotates_within_relevance_band() -> None:
    strong = [_record(index, classic=index < 4, relevance=10.0) for index in range(12)]
    weak = [_record(100 + index, classic=False, relevance=0.01) for index in range(20)]
    records = strong + weak

    first, _ = rank_discovery(records, query="attention", limit=10, seed="same")
    again, _ = rank_discovery(records, query="attention", limit=10, seed="same")
    rotated, _ = rank_discovery(records, query="attention", limit=10, seed="different")

    assert [item.record.external_ids for item in first] == [
        item.record.external_ids for item in again
    ]
    assert [item.record.external_ids for item in first] != [
        item.record.external_ids for item in rotated
    ]
    assert all((item.record.source_score or 0) >= 10.0 for item in first)
    assert all((item.record.source_score or 0) >= 10.0 for item in rotated)


def test_discovery_reports_classic_shortfall_without_manufacturing_labels() -> None:
    records = [_record(index, classic=False) for index in range(50)]
    ranked, composition = rank_discovery(records, query="attention", limit=50, seed="seed")
    assert [item.label for item in ranked].count("classic_candidate") == 0
    assert composition.classic_shortfall == 10
