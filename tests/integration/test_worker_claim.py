from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from services.worker.main import _claim_job, execute_job, run_once

from research_navigator.config import Settings
from research_navigator.db import Database
from research_navigator.models import Job, User


def settings_for(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'worker.db'}",
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        backup_dir=tmp_path / "backups",
        allowed_origins=("http://localhost:5173",),
        session_ttl_hours=24,
        enable_fixture_source=True,
        enable_openalex=False,
        enable_crossref=False,
        enable_arxiv=False,
        enable_semantic_scholar=False,
        semantic_scholar_api_key=None,
        unpaywall_email=None,
        crossref_mailto=None,
        llm_base_url=None,
        llm_api_key=None,
        llm_model=None,
        max_pdf_bytes=25 * 1024 * 1024,
        environment="test",
    )


def test_two_workers_claim_one_job(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    database = Database.from_url(settings.database_url)
    database.init()
    with database.session() as session:
        user = User(
            email="worker-claim@example.com",
            password_hash="not-used",
            display_name="Worker",
        )
        session.add(user)
        session.flush()
        session.add(Job(user_id=user.id, job_type="noop", payload_json='{"value": 1}'))
        session.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda worker: run_once(database, worker_id=worker, settings=settings),
                ("worker-a", "worker-b"),
            )
        )

    assert sorted(result for result in results if result is not None) == [1]


def test_claim_uses_a_single_atomic_transition(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    database = Database.from_url(settings.database_url)
    database.init()
    with database.session() as session:
        user = User(email="atomic@example.com", password_hash="x", display_name="Atomic")
        session.add(user)
        session.flush()
        session.add(Job(user_id=user.id, job_type="noop", payload_json="{}"))
        session.commit()

    with database.session() as session:
        job = _claim_job(session, worker_id="worker-a")
        assert job is not None
        assert job.status == "running"
        assert job.locked_by == "worker-a"
        assert job.attempt_count == 1
        assert _claim_job(session, worker_id="worker-b") is None


def test_bounded_executor_is_idempotent_for_retried_trigger(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    database = Database.from_url(settings.database_url)
    database.init()
    with database.session() as session:
        user = User(email="executor@example.com", password_hash="x", display_name="Executor")
        session.add(user)
        session.flush()
        row = Job(user_id=user.id, job_type="noop", payload_json='{"value": 3}')
        session.add(row)
        session.commit()
        job_id = row.id

    assert execute_job(database, job_id=job_id, worker_id="serverless-1", settings=settings)
    assert not execute_job(database, job_id=job_id, worker_id="serverless-retry", settings=settings)

    with database.session() as session:
        job = session.get(Job, job_id)
        assert job is not None
        assert job.status == "succeeded"
        assert job.attempt_count == 1
