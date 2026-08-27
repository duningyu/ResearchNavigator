from research_navigator.open_access.base import OpenAccessCandidate
from research_navigator.open_access.policy import decide_access


def candidate(**updates: object) -> OpenAccessCandidate:
    values: dict[str, object] = {
        "source": "openalex",
        "source_record_id": "W1",
        "landing_url": "https://repository.example/paper",
        "pdf_url": "https://repository.example/paper.pdf",
        "license": "CC-BY-4.0",
        "host_type": "repository",
        "version": "acceptedVersion",
        "is_oa": True,
        "requires_auth": False,
        "provenance_hash": "a" * 64,
    }
    values.update(updates)
    return OpenAccessCandidate.model_validate(values)


def test_permissive_license_is_auto_ingest() -> None:
    evaluated = decide_access(candidate(license="https://creativecommons.org/licenses/by/4.0/"))
    assert evaluated.access_decision == "auto_ingest"
    assert evaluated.normalized_license == "cc-by"
    assert evaluated.rejection_reason is None


def test_limited_license_requires_user_confirmation() -> None:
    evaluated = decide_access(candidate(license="CC BY-NC-ND 4.0"))
    assert evaluated.access_decision == "requires_user_confirmation"
    assert evaluated.normalized_license == "cc-by-nc-nd"


def test_unknown_license_is_link_only() -> None:
    evaluated = decide_access(candidate(license=None))
    assert evaluated.access_decision == "link_only"
    assert evaluated.rejection_reason == "license_unknown"


def test_non_oa_or_credentialed_or_unsafe_url_is_rejected() -> None:
    assert decide_access(candidate(is_oa=False)).access_decision == "rejected"
    assert decide_access(candidate(requires_auth=True)).rejection_reason == "authentication_required"
    assert (
        decide_access(candidate(pdf_url="https://user:secret@example.org/paper.pdf")).rejection_reason
        == "url_contains_userinfo"
    )
    assert decide_access(candidate(pdf_url="ftp://example.org/paper.pdf")).rejection_reason == "unsupported_url_scheme"


def test_oa_landing_page_without_pdf_is_link_only() -> None:
    evaluated = decide_access(candidate(pdf_url=None))
    assert evaluated.access_decision == "link_only"
    assert evaluated.rejection_reason == "pdf_url_unavailable"
