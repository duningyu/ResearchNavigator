"""Material identity is independent of successful download and content hashes."""

from research_navigator.documents.material_binding import bind_material
from research_navigator.documents.parser import ParsedDocument, ParsedPage
from research_navigator.scholarly.base import PaperRecord
from research_navigator.scholarly.normalize import normalize_record


def bind(text: str, expected: str = "2401.12345v2") -> dict:
    return bind_material(
        paper_id=7,
        arxiv_id=expected,
        doi=None,
        sha256="a" * 64,
        parsed=ParsedDocument(pages=(ParsedPage(page_number=1, text=text),)),
    )


def test_correct_explicit_version_can_enter_analysis():
    result = bind("arXiv:2401.12345v2\nAbstract\nA synthetic experiment.")
    assert result["status"] == "verified"
    assert result["actual_version"] == "2401.12345v2"
    assert result["paper_id"] == 7


def test_wrong_paper_cannot_be_bound_by_sha():
    assert bind("arXiv:2401.99999v2\nAbstract\nOther paper.")["status"] == "identity_mismatch"


def test_old_version_is_not_current():
    assert bind("arXiv:2401.12345v1\nAbstract\nOlder material.")["status"] == "version_mismatch"


def test_unversioned_record_does_not_assert_latest():
    assert bind("arXiv:2401.12345v2\nAbstract", "2401.12345")["status"] == "version_unconfirmed"


def test_no_identifier_keeps_identity_unknown():
    assert bind("Similar title\nAbstract\nSynthetic text.")["status"] == "identity_unconfirmed"


def test_reference_identifier_does_not_prove_material_identity():
    assert bind("Other paper\nReferences\narXiv:2401.12345v2")["status"] == "identity_unconfirmed"


def test_explicit_version_does_not_override_recorded_conflict():
    from research_navigator.documents.material_binding import expected_arxiv_identity
    from research_navigator.models import Paper

    paper = Paper(
        title="Conflicting versions",
        normalized_title="conflicting versions",
        arxiv_id="2401.12345v2",
        external_ids_json='{"arxiv_version_conflict": true}',
    )
    assert expected_arxiv_identity(paper) is None


def test_normalization_keeps_version_separate_from_dedup_identity():
    record = normalize_record(PaperRecord(title="Synthetic", arxiv_id="2401.12345v2"))
    assert record.arxiv_id == "2401.12345"
    assert record.external_ids["arxiv_versioned_id"] == "2401.12345v2"
    assert normalize_record(record).external_ids == record.external_ids


def test_upsert_does_not_silently_reuse_old_version_binding():
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from research_navigator.documents.material_binding import expected_arxiv_identity
    from research_navigator.models import Base
    from research_navigator.scholarly.base import PaperRecord
    from research_navigator.scholarly.repository import upsert_paper

    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        old = upsert_paper(session, PaperRecord(title="Versioned study", arxiv_id="2401.12345v2"))
        assert expected_arxiv_identity(old) == "2401.12345v2"
        updated = upsert_paper(
            session, PaperRecord(title="Versioned study", arxiv_id="2401.12345v3")
        )
        assert updated.id == old.id
        assert expected_arxiv_identity(updated) is None, (
            "Conflicting source versions need reconciliation"
        )
    engine.dispose()
