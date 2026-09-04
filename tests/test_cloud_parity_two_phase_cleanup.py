from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(
    0,
    str(Path(__file__).parents[1] / "deployment" / "cloud" / "parity"),
)


def test_docker_flow_requires_distinct_prepare_and_reload_invocations() -> None:
    from run_evidence_workflow_parity import build_phase_plan

    plan = build_phase_plan()
    assert plan == ("prepare", "reload")
    assert plan[0] != plan[1]


def test_prepare_contract_includes_paper_id() -> None:
    from run_evidence_workflow_parity import prepare_payload

    payload = prepare_payload(
        execution_id="e",
        job_id=1,
        document_id=2,
        user_id=3,
        paper_id=4,
        input_key="input",
        stored_key="stored",
        fixture_sha256="a" * 64,
    )
    assert json.loads(payload)["paper_id"] == 4


def test_cleanup_scope_rejects_wrong_fixture_owner() -> None:
    from run_evidence_workflow_parity import FixtureOwnershipError, validate_fixture_ownership

    with pytest.raises(FixtureOwnershipError):
        validate_fixture_ownership(
            execution_id="expected",
            fixture_sha256="a" * 64,
            user_email="other@example.invalid",
            paper_doi="10.9999/other",
            document_run_id="expected",
            document_sha256="a" * 64,
            job_user_id=1,
            document_user_id=1,
            requested_user_id=2,
        )


def test_cleanup_scope_accepts_only_exact_synthetic_fixture() -> None:
    from run_evidence_workflow_parity import validate_fixture_ownership

    validate_fixture_ownership(
        execution_id="expected",
        fixture_sha256="a" * 64,
        user_email="rn223-parity-expected@example.invalid",
        paper_doi="10.9999/rn223-parity-expected",
        document_run_id="expected",
        document_sha256="a" * 64,
        job_user_id=2,
        document_user_id=2,
        requested_user_id=2,
    )


def test_recovery_command_is_explicit_and_does_not_prepare() -> None:
    from run_evidence_workflow_parity import build_phase_plan

    assert build_phase_plan(recovery=True) == ("recover",)


def test_exact_cleanup_removes_fixture_dependents_but_preserves_unrelated_rows() -> None:
    from run_evidence_workflow_parity import _assert_fixture_rows_absent, _delete_fixture_rows

    from research_navigator.models import (
        Base,
        Job,
        JobEvent,
        Paper,
        PaperAnalysisRecord,
        PaperChunk,
        PaperDocument,
        User,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE VIRTUAL TABLE paper_chunks_fts USING fts5("
                "text, document_id UNINDEXED, chunk_id UNINDEXED)"
            )
        )
    with Session(engine) as session:
        fixture_user = User(
            email="rn223-parity-cleanup@example.invalid",
            password_hash="x",
            display_name="fixture",
        )
        other_user = User(
            email="rn223-parity-other@example.invalid",
            password_hash="x",
            display_name="other",
        )
        session.add_all([fixture_user, other_user])
        session.flush()
        fixture_paper = Paper(title="fixture", normalized_title="fixture", doi="10.9999/fixture")
        other_paper = Paper(title="other", normalized_title="other", doi="10.9999/other")
        session.add_all([fixture_paper, other_paper])
        session.flush()
        fixture_document = PaperDocument(
            user_id=fixture_user.id, paper_id=fixture_paper.id, source_type="open_access",
            evidence_level="primary", original_filename="fixture.pdf", stored_path="fixture",
            mime_type="application/pdf", sha256="a" * 64, size_bytes=1, page_count=1,
            acquisition_run_id="cleanup-execution",
        )
        fixture_document_derived = PaperDocument(
            user_id=fixture_user.id, paper_id=fixture_paper.id, source_type="derived",
            evidence_level="primary", original_filename="fixture-derived.pdf",
            stored_path="fixture-derived", mime_type="application/pdf", sha256="d" * 64,
            size_bytes=1, page_count=1, acquisition_run_id="cleanup-execution",
        )
        other_document = PaperDocument(
            user_id=other_user.id, paper_id=other_paper.id, source_type="open_access",
            evidence_level="primary", original_filename="other.pdf", stored_path="other",
            mime_type="application/pdf", sha256="b" * 64, size_bytes=1, page_count=1,
        )
        session.add_all([fixture_document, fixture_document_derived, other_document])
        session.flush()
        fixture_job = Job(
            user_id=fixture_user.id, job_type="evidence_workflow_v1", status="succeeded"
        )
        other_job = Job(
            user_id=other_user.id, job_type="evidence_workflow_v1", status="succeeded"
        )
        session.add_all([fixture_job, other_job])
        session.flush()
        session.add_all([
            JobEvent(job_id=fixture_job.id, user_id=fixture_user.id, event_type="done"),
            JobEvent(job_id=other_job.id, user_id=other_user.id, event_type="done"),
            PaperChunk(
                document_id=fixture_document.id,
                paper_id=fixture_paper.id,
                user_id=fixture_user.id,
                section="body", page_start=1, page_end=1, chunk_index=0, text="fixture",
                text_hash="c" * 64,
                vector_json="[]",
                source_type="open_access",
                evidence_level="primary",
            ),
            PaperAnalysisRecord(
                user_id=fixture_user.id, paper_id=fixture_paper.id, evidence_level="primary",
                analysis_version="test", analysis_json="{}", direction_similarity_json="{}",
                reproduction_assessment_json="{}", analysis_run_id="cleanup-run",
            ),
        ])
        session.flush()
        session.execute(
            text(
                "INSERT INTO paper_chunks_fts(text, document_id, chunk_id) "
                "VALUES ('fixture', :document_id, 1)"
            ),
            {"document_id": fixture_document.id},
        )
        session.commit()
        fixture_user_id = fixture_user.id
        fixture_paper_id = fixture_paper.id
        fixture_document_id = fixture_document.id
        fixture_job_id = fixture_job.id
        other_user_id = other_user.id
        other_paper_id = other_paper.id
        other_document_id = other_document.id
        other_job_id = other_job.id

        _delete_fixture_rows(
            session,
            user_id=fixture_user_id,
            paper_id=fixture_paper_id,
            document_id=fixture_document_id,
            job_id=fixture_job_id,
        )
        session.commit()
        _assert_fixture_rows_absent(
            session,
            user_id=fixture_user_id,
            paper_id=fixture_paper_id,
            document_id=fixture_document_id,
            job_id=fixture_job_id,
        )
        assert session.get(User, other_user_id) is not None
        assert session.get(Paper, other_paper_id) is not None
        assert session.get(PaperDocument, other_document_id) is not None
        assert session.get(Job, other_job_id) is not None
        assert session.query(JobEvent).filter(JobEvent.job_id == other_job_id).count() == 1


def test_cleanup_assertion_uses_database_state_after_bulk_delete() -> None:
    from run_evidence_workflow_parity import _assert_fixture_rows_absent, _delete_fixture_rows

    from research_navigator.models import Base, Paper, PaperDocument, User

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE VIRTUAL TABLE paper_chunks_fts USING fts5("
                "text, document_id UNINDEXED, chunk_id UNINDEXED)"
            )
        )
    with Session(engine, expire_on_commit=False) as session:
        user = User(
            email="rn223-parity-stale-state@example.invalid",
            password_hash="x",
            display_name="fixture",
        )
        paper = Paper(title="fixture", normalized_title="fixture", doi="10.9999/stale")
        session.add_all([user, paper])
        session.flush()
        document = PaperDocument(
            user_id=user.id,
            paper_id=paper.id,
            source_type="open_access",
            evidence_level="primary",
            original_filename="fixture.pdf",
            stored_path="fixture",
            mime_type="application/pdf",
            sha256="a" * 64,
            size_bytes=1,
            page_count=1,
            acquisition_run_id="stale-state-execution",
        )
        session.add(document)
        session.flush()
        user_id, paper_id, document_id = user.id, paper.id, document.id
        session.commit()

        # Mirror reload_and_cleanup(): the identity map contains the row before
        # Core bulk DELETE and expire_on_commit=False preserves that object.
        assert session.get(PaperDocument, document_id) is not None
        _delete_fixture_rows(
            session,
            user_id=user_id,
            paper_id=paper_id,
            document_id=document_id,
            job_id=999,
        )
        session.commit()

        # A recovery retry may repeat cleanup after the first attempt already
        # removed the fixture. The exact cleanup operation must be idempotent.
        _delete_fixture_rows(
            session,
            user_id=user_id,
            paper_id=paper_id,
            document_id=document_id,
            job_id=999,
        )
        session.commit()

        _assert_fixture_rows_absent(
            session,
            user_id=user_id,
            paper_id=paper_id,
            document_id=document_id,
            job_id=999,
        )


@pytest.mark.parametrize(
    ("remove_job", "remove_document"),
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_recovery_converges_from_partial_root_state(
    remove_job: bool, remove_document: bool
) -> None:
    from run_evidence_workflow_parity import (
        _delete_fixture_rows,
        _recovery_owned_rows,
    )

    from research_navigator.models import Base, Job, Paper, PaperDocument, User

    execution_id = "recovery-partial-state"
    fixture_sha = "a" * 64
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE VIRTUAL TABLE paper_chunks_fts USING fts5("
                "text, document_id UNINDEXED, chunk_id UNINDEXED)"
            )
        )
    with Session(engine) as session:
        user = User(
            email=f"rn223-parity-{execution_id}@example.invalid",
            password_hash="x",
            display_name="fixture",
        )
        paper = Paper(
            title="fixture", normalized_title="fixture", doi=f"10.9999/rn223-parity-{execution_id}"
        )
        session.add_all([user, paper])
        session.flush()
        document = PaperDocument(
            user_id=user.id,
            paper_id=paper.id,
            source_type="open_access",
            evidence_level="primary",
            original_filename="fixture.pdf",
            stored_path=f"{user.id}/{paper.id}/oa/{fixture_sha}.pdf",
            mime_type="application/pdf",
            sha256=fixture_sha,
            size_bytes=1,
            page_count=1,
            acquisition_run_id=execution_id,
        )
        job = Job(user_id=user.id, job_type="evidence_workflow_v1", status="succeeded")
        session.add_all([document, job])
        session.flush()
        user_id, paper_id, document_id, job_id = user.id, paper.id, document.id, job.id
        if remove_job:
            session.delete(job)
        if remove_document:
            session.delete(document)
        session.flush()

        resolved = _recovery_owned_rows(
            session,
            execution_id=execution_id,
            fixture_sha256=fixture_sha,
            requested_user_id=user_id,
            requested_paper_id=paper_id,
            requested_job_id=job_id,
            requested_document_id=document_id,
        )
        resolved_user, resolved_paper, document_ids, job_ids, _ = resolved
        _delete_fixture_rows(
            session,
            user_id=resolved_user,
            paper_id=resolved_paper,
            # Keep verified primary-key anchors even after their rows were
            # removed, so remaining dependent rows are still swept exactly.
            document_id=document_id,
            job_id=job_id,
            document_ids=document_ids,
        )
        session.commit()
        assert session.get(User, user_id) is None
        assert session.get(Paper, paper_id) is None
        assert session.get(PaperDocument, document_id) is None
        assert session.get(Job, job_id) is None


def test_normalized_recovery_key_is_exact_and_fixture_scoped() -> None:
    from run_evidence_workflow_parity import (
        FixtureOwnershipError,
        validate_recovery_stored_key,
    )

    validate_recovery_stored_key(
        "2/3/oa/" + "a" * 64 + ".pdf",
        user_id=2,
        paper_id=3,
        fixture_sha256="a" * 64,
    )
    with pytest.raises(FixtureOwnershipError):
        validate_recovery_stored_key(
            "2/3/oa/" + "b" * 64 + ".pdf",
            user_id=2,
            paper_id=3,
            fixture_sha256="a" * 64,
        )


def test_normal_reload_contract_remains_strict() -> None:
    from run_evidence_workflow_parity import build_phase_plan

    assert build_phase_plan() == ("prepare", "reload")
    assert build_phase_plan(recovery=True) == ("recover",)
