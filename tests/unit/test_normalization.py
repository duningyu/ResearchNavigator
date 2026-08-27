from research_navigator.scholarly.normalize import (
    normalize_arxiv_id,
    normalize_doi,
    normalize_title,
)


def test_identifier_normalization_removes_wrappers_and_versions() -> None:
    assert normalize_doi("https://doi.org/10.1145/ABC.123") == "10.1145/abc.123"
    assert normalize_doi("doi: 10.1000/XYZ") == "10.1000/xyz"
    assert normalize_arxiv_id("arXiv:2301.01234v2") == "2301.01234"


def test_title_normalization_is_unicode_and_punctuation_stable() -> None:
    left = normalize_title("Anomaly Transformer: Time-Series Detection")
    right = normalize_title("  anomaly transformer — time series detection ")
    assert left == right
