from research_navigator.documents.open_evidence import (
    OpenMaterialCandidate,
    classify_cache_policy,
    expected_arxiv_identity,
)


def test_unknown_license_is_not_shared_durable() -> None:
    assert classify_cache_policy(
        source="openalex",
        license=None,
        rights_basis="oa_location_without_license",
    ) == "not_cacheable"


def test_approved_license_can_be_shared_durable() -> None:
    assert classify_cache_policy(
        source="arxiv",
        license="http://creativecommons.org/licenses/by/4.0/",
        rights_basis="arxiv_license",
    ) == "shared_durable"


def test_public_candidate_binds_to_exact_arxiv_identity() -> None:
    candidate = OpenMaterialCandidate(
        source="arxiv",
        source_record_id="2401.12345v2",
        pdf_url="https://arxiv.org/pdf/2401.12345v2",
        rights_basis="arxiv_license",
        cache_policy="shared_durable",
    )
    assert expected_arxiv_identity("2401.12345v2") == candidate.source_record_id
    assert expected_arxiv_identity("2401.12345v1") != candidate.source_record_id
