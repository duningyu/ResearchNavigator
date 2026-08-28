from research_navigator.authors.service import canonical_author_identity


def test_orcid_is_stable_identity() -> None:
    assert (
        canonical_author_identity(
            name="Jane Doe",
            orcid="https://orcid.org/0000-0002-1825-0097",
            source="openalex",
            source_author_id="A1",
        )
        == "orcid:0000-0002-1825-0097"
    )


def test_source_id_is_used_when_orcid_absent() -> None:
    assert (
        canonical_author_identity(
            name="Jane Doe", orcid=None, source="openalex", source_author_id="A1"
        )
        == "source:openalex:A1"
    )


def test_name_only_identity_is_scoped_and_not_global_merge_key() -> None:
    first = canonical_author_identity(
        name="Wei Zhang", orcid=None, source=None, source_author_id=None, paper_id=1, position=0
    )
    second = canonical_author_identity(
        name="Wei Zhang", orcid=None, source=None, source_author_id=None, paper_id=2, position=0
    )
    assert first != second
    assert first.startswith("unresolved:")
