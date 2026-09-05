from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT))

from deployment.cloud.acceptance.preview_fixture_controller import (  # noqa: E402
    DatabaseIdentityError,
    FixtureManifest,
    OwnershipAmbiguous,
    collect_cleanup_plan,
    execute_cleanup,
    freeze_manifest,
    manifest_sha256,
    validate_database_host,
    validate_database_identity,
    validate_manifest,
    verify_cleanup,
)

from research_navigator.models import (  # noqa: E402
    Base,
    Favorite,
    Paper,
    PaperSet,
    PaperSetItem,
    ResearchProject,
    User,
)


class MemoryObjectStore:
    def __init__(self, keys: list[str]) -> None:
        self.keys = set(keys)

    def head(self, key: str) -> bool:
        return key in self.keys

    def delete(self, key: str) -> None:
        self.keys.remove(key)


@pytest.fixture()
def db_factory() -> sessionmaker:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _fixture(db_factory: sessionmaker) -> tuple[FixtureManifest, int, int, int, int]:
    with db_factory() as session:
        account = User(
            email="acceptance-owner@example.invalid",
            password_hash="not-a-real-password",
            display_name="Acceptance Owner",
        )
        unrelated = User(
            email="unrelated@example.invalid",
            password_hash="not-a-real-password",
            display_name="Unrelated",
        )
        project = ResearchProject(user=account, name="RN223 Acceptance rn223-preview-fixture-test")
        unrelated_project = ResearchProject(user=unrelated, name="Unrelated project")
        borrowed = Paper(title="Borrowed paper", normalized_title="borrowed paper")
        unrelated_paper = Paper(title="Unrelated paper", normalized_title="unrelated paper")
        session.add_all([account, unrelated, project, unrelated_project, borrowed, unrelated_paper])
        session.flush()
        favorite = Favorite(user_id=account.id, paper_id=borrowed.id)
        unrelated_favorite = Favorite(user_id=account.id, paper_id=unrelated_paper.id)
        paper_set = PaperSet(
            user_id=account.id,
            project_id=project.id,
            purpose="acceptance",
            name="RN223 Acceptance Set rn223-preview-fixture-test",
        )
        session.add_all([favorite, unrelated_favorite, paper_set])
        session.flush()
        item = PaperSetItem(paper_set_id=paper_set.id, paper_id=borrowed.id, position=0)
        session.add(item)
        session.commit()
        manifest = FixtureManifest(
            execution_id="rn223-preview-fixture-test",
            deployed_source_commit="deployed",
            acceptance_tool_commit="local",
            preview_host="https://preview.example.invalid",
            account_user_id=account.id,
            account_identity_hash=hashlib.sha256(account.email.encode()).hexdigest(),
            project_ids=[project.id],
            borrowed_paper_ids=[borrowed.id],
            favorite_ids=[favorite.id],
            paper_set_ids=[paper_set.id],
            paper_set_item_ids=[item.id],
            r2_object_keys=["uploads/fixture/test.pdf"],
        )
        freeze_manifest(manifest)
        return manifest, account.id, unrelated_project.id, unrelated_favorite.id, borrowed.id


def test_dry_run_plan_is_non_mutating_and_cleanup_is_exact(db_factory: sessionmaker) -> None:
    manifest, account_id, unrelated_project_id, unrelated_favorite_id, borrowed_id = _fixture(
        db_factory
    )
    with db_factory() as session:
        before = collect_cleanup_plan(session, manifest)
    assert before["favorites"] and before["paper_sets"]
    store = MemoryObjectStore(manifest.r2_object_keys + ["uploads/unrelated/keep.pdf"])
    execute_cleanup(db_factory, manifest, manifest_sha256(manifest), object_store=store)
    with db_factory() as session:
        assert session.get(User, account_id) is not None
        assert session.get(ResearchProject, unrelated_project_id) is not None
        assert session.get(Favorite, unrelated_favorite_id) is not None
        assert session.get(Paper, borrowed_id) is not None
        assert session.get(PaperSet, manifest.paper_set_ids[0]) is None
    assert store.keys == {"uploads/unrelated/keep.pdf"}


def test_execute_requires_frozen_manifest_hash_and_rejects_tampering(
    db_factory: sessionmaker,
) -> None:
    manifest, *_ = _fixture(db_factory)
    with pytest.raises(OwnershipAmbiguous):
        execute_cleanup(db_factory, manifest, "0" * 64)
    manifest.favorite_ids.append(999999)
    with pytest.raises(OwnershipAmbiguous):
        verify_cleanup(db_factory, manifest, object_store=MemoryObjectStore([]))


def test_database_identity_rejects_old_or_non_turso() -> None:
    validate_database_identity(backend="turso", target_database="researchnavigator-rn223")
    with pytest.raises(DatabaseIdentityError):
        validate_database_identity(backend="turso", target_database="researchnavigator")
    with pytest.raises(DatabaseIdentityError):
        validate_database_identity(backend="sqlite", target_database="researchnavigator-rn223")
    validate_database_host(
        target_database="researchnavigator-rn223",
        database_url="libsql://researchnavigator-rn223-duningyu.aws-us-east-1.turso.io",
    )
    with pytest.raises(DatabaseIdentityError):
        validate_database_host(
            target_database="researchnavigator-rn223",
            database_url="libsql://researchnavigator.aws-us-east-1.turso.io",
        )


def test_manifest_rejects_unsafe_r2_key() -> None:
    manifest = FixtureManifest(
        execution_id="rn223-preview-fixture-test",
        deployed_source_commit="deployed",
        acceptance_tool_commit="local",
        preview_host="https://preview.example.invalid",
        account_user_id=1,
        account_identity_hash="a" * 64,
        r2_object_keys=["../other-fixture/object.pdf"],
    )
    with pytest.raises(OwnershipAmbiguous):
        validate_manifest(manifest)


def test_partial_cleanup_is_idempotent_and_r2_absence_is_success(db_factory: sessionmaker) -> None:
    manifest, *_ = _fixture(db_factory)
    store = MemoryObjectStore(manifest.r2_object_keys)
    execute_cleanup(db_factory, manifest, manifest_sha256(manifest), object_store=store)
    execute_cleanup(db_factory, manifest, manifest_sha256(manifest), object_store=store)
    assert verify_cleanup(db_factory, manifest, object_store=store)["database_rows_after"] == 0


def test_cross_owned_row_fails_closed(db_factory: sessionmaker) -> None:
    manifest, *_ = _fixture(db_factory)
    with db_factory() as session:
        other = session.scalar(select(User).where(User.email == "unrelated@example.invalid"))
        row = Favorite(user_id=other.id, paper_id=manifest.borrowed_paper_ids[0])
        session.add(row)
        session.flush()
        manifest.favorite_ids.append(row.id)
        with pytest.raises(OwnershipAmbiguous):
            collect_cleanup_plan(session, manifest)


def test_account_identity_mismatch_fails_closed(db_factory: sessionmaker) -> None:
    manifest, *_ = _fixture(db_factory)
    manifest.account_identity_hash = "0" * 64
    with db_factory() as session, pytest.raises(OwnershipAmbiguous, match="account identity"):
        collect_cleanup_plan(session, manifest)


def test_acceptance_controller_is_not_in_application_import_graph() -> None:
    application_files = list((ROOT / "apps" / "api" / "research_navigator").rglob("*.py"))
    assert all(
        "deployment.cloud.acceptance" not in path.read_text(encoding="utf-8")
        for path in application_files
    )
