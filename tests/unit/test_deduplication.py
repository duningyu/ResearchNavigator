from research_navigator.scholarly.base import PaperAuthor, PaperRecord, SourceProvenance
from research_navigator.scholarly.normalize import deduplicate_records


def test_deduplicate_prefers_stable_identifier_and_merges_provenance() -> None:
    first = PaperRecord(
        title="A Reliable Paper",
        abstract="Short abstract.",
        publication_year=2024,
        authors=[PaperAuthor(name="Alice")],
        doi="https://doi.org/10.1000/ABC",
        source_urls=["https://source-a.example/paper"],
        source_provenance=[SourceProvenance(source="openalex", source_id="W1", is_fixture=False)],
    )
    second = PaperRecord(
        title="A Reliable Paper",
        abstract="A longer abstract containing useful method and experiment details.",
        publication_year=2024,
        authors=[PaperAuthor(name="Alice", orcid="0000-0000-0000-0001")],
        doi="10.1000/abc",
        source_urls=["https://source-b.example/paper"],
        source_provenance=[
            SourceProvenance(source="crossref", source_id="10.1000/abc", is_fixture=False)
        ],
    )

    merged = deduplicate_records([first, second])

    assert len(merged) == 1
    assert merged[0].doi == "10.1000/abc"
    assert merged[0].abstract == second.abstract
    assert {item.source for item in merged[0].source_provenance} == {"openalex", "crossref"}
    assert len(merged[0].source_urls) == 2
