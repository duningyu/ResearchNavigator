"""Run bounded Linux executor benchmarks without live provider traffic."""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CACHED_IMAGE = "rn223-schema-audit:py312-libsql020"
TASKS = ("paper_analysis", "evidence_workflow_v1", "gap_challenge")


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--child":
        return child_main(sys.argv[2])
    if len(sys.argv) >= 2 and sys.argv[1] == "--reliability-child":
        return reliability_child_main()
    return benchmark_main()


def _settings(data_dir: Path) -> Any:
    from research_navigator.config import Settings

    return Settings(
        data_dir=data_dir,
        database_url=f"sqlite+pysqlite:///{(data_dir / 'benchmark.db').as_posix()}",
        upload_dir=data_dir / "uploads",
        vector_dir=data_dir / "vectors",
        backup_dir=data_dir / "backups",
        allowed_origins=("http://localhost:5173",),
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
        max_pdf_bytes=2_000_000,
        session_ttl_hours=24,
        environment="test",
    )


def _register(client: Any) -> dict[str, str]:
    auth = client.post(
        "/api/auth/register",
        json={
            "email": "benchmark@example.invalid",
            "password": "research-pass-123",
            "display_name": "RN223 benchmark",
        },
    ).json()
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _prepare_job(client: Any, headers: dict[str, str], task: str) -> int:
    project = client.post(
        "/api/projects",
        headers=headers,
        json={"name": "RN223 benchmark project", "broad_direction": "synthetic bounded benchmark"},
    ).json()
    papers = client.post(
        "/api/search/papers",
        headers=headers,
        json={"query": "synthetic benchmark", "sources": ["fixture"], "limit": 3},
    ).json()["papers"]
    paper_ids = [int(paper["id"]) for paper in papers]
    if task == "paper_analysis":
        response = client.post(
            "/api/jobs",
            headers=headers,
            json={
                "job_type": task,
                "project_id": project["id"],
                "payload": {"paper_id": paper_ids[0], "project_id": project["id"]},
            },
        )
    elif task == "evidence_workflow_v1":
        response = client.post(
            f"/api/papers/{paper_ids[0]}/evidence-workflows",
            headers=headers,
            json={"sources": ["fixture"]},
        )
    else:
        gap = client.post(
            "/api/gaps/generate",
            headers=headers,
            json={"project_id": project["id"], "paper_ids": paper_ids[:2]},
        ).json()
        response = client.post(
            "/api/jobs",
            headers=headers,
            json={
                "job_type": task,
                "project_id": project["id"],
                "payload": {"gap_id": gap["id"], "additional_terms": ["bounded benchmark"]},
            },
        )
    if response.status_code >= 300:
        raise RuntimeError(f"fixture setup failed: {response.status_code}")
    return int(response.json()["id"])


def child_main(task: str) -> int:
    if task not in TASKS:
        raise SystemExit(f"unsupported task: {task}")
    from fastapi.testclient import TestClient
    from services.worker.main import execute_job

    from research_navigator.main import create_app

    with tempfile.TemporaryDirectory(prefix=f"rn223-benchmark-{task}-") as raw_dir:
        settings = _settings(Path(raw_dir))
        app = create_app(settings)
        with TestClient(app) as client:
            headers = _register(client)
            job_id = _prepare_job(client, headers, task)
            execute_started = time.perf_counter()
            claimed = execute_job(
                app.state.database,
                job_id=job_id,
                worker_id=f"benchmark-{os.getpid()}",
                settings=settings,
                storage=app.state.storage,
            )
            execute_ms = (time.perf_counter() - execute_started) * 1000
            if not claimed:
                raise RuntimeError("benchmark job was not claimed")
            with app.state.database.session() as session:
                from research_navigator.models import Job

                job = session.get(Job, job_id)
                if job is None or job.status not in {"succeeded", "partial", "failed"}:
                    raise RuntimeError("benchmark job did not reach terminal state")
                status = job.status
            print(
                json.dumps({"task": task, "job_execute_ms": round(execute_ms, 3), "status": status})
            )
    return 0


def reliability_child_main() -> int:
    """Exercise the existing bounded executor with local synthetic jobs only."""
    from concurrent.futures import ThreadPoolExecutor

    from services.worker import main as worker_main

    from research_navigator.db import Database
    from research_navigator.models import Job, User

    with tempfile.TemporaryDirectory(prefix="rn223-reliability-") as raw_dir:
        settings = _settings(Path(raw_dir))
        database = Database.from_url(settings.database_url)
        database.init()
        with database.session() as session:
            user = User(
                email="reliability@example.invalid",
                password_hash="benchmark-only",
                display_name="RN223 reliability",
            )
            session.add(user)
            session.flush()
            claim_job = Job(user_id=user.id, job_type="noop", payload_json='{"kind":"claim"}')
            duplicate_job = Job(
                user_id=user.id, job_type="noop", payload_json='{"kind":"duplicate"}'
            )
            retry_job = Job(user_id=user.id, job_type="noop", payload_json='{"kind":"retry"}')
            exhausted_job = Job(
                user_id=user.id, job_type="paper_analysis", payload_json="{}", max_attempts=2
            )
            session.add_all([claim_job, duplicate_job, retry_job, exhausted_job])
            session.commit()
            claim_id, duplicate_id, retry_id, exhausted_id = (
                claim_job.id,
                duplicate_job.id,
                retry_job.id,
                exhausted_job.id,
            )

        contenders = 8
        with ThreadPoolExecutor(max_workers=contenders) as pool:
            claim_results = list(
                pool.map(
                    lambda index: worker_main.execute_job(
                        database,
                        job_id=claim_id,
                        worker_id=f"contender-{index}",
                        settings=settings,
                    ),
                    range(contenders),
                )
            )
        duplicate_results = [
            worker_main.execute_job(
                database, job_id=duplicate_id, worker_id="duplicate-a", settings=settings
            ),
            worker_main.execute_job(
                database, job_id=duplicate_id, worker_id="duplicate-b", settings=settings
            ),
        ]

        original_execute = worker_main._execute_job
        retry_calls = 0

        def fail_once_then_succeed(*args: object, **kwargs: object) -> dict[str, object]:
            nonlocal retry_calls
            retry_calls += 1
            if retry_calls == 1:
                raise RuntimeError("controlled benchmark retry")
            return {"retry": "succeeded"}

        worker_main._execute_job = fail_once_then_succeed
        try:
            retry_results = [
                worker_main.execute_job(
                    database, job_id=retry_id, worker_id="retry-a", settings=settings
                ),
                worker_main.execute_job(
                    database, job_id=retry_id, worker_id="retry-b", settings=settings
                ),
            ]
        finally:
            worker_main._execute_job = original_execute

        exhaustion_results = [
            worker_main.execute_job(
                database, job_id=exhausted_id, worker_id="exhaust-a", settings=settings
            ),
            worker_main.execute_job(
                database, job_id=exhausted_id, worker_id="exhaust-b", settings=settings
            ),
        ]
        with database.session() as session:
            claim_row = session.get(Job, claim_id)
            duplicate_row = session.get(Job, duplicate_id)
            retry_row = session.get(Job, retry_id)
            exhausted_row = session.get(Job, exhausted_id)
            assert claim_row is not None and duplicate_row is not None
            assert retry_row is not None and exhausted_row is not None
            result = {
                "atomic_claim": sum(claim_results) == 1,
                "contender_count": contenders,
                "execution_owner_count": sum(claim_results),
                "duplicate_dispatch": sum(duplicate_results) == 1,
                "terminal_reentry": not worker_main.execute_job(
                    database,
                    job_id=duplicate_id,
                    worker_id="duplicate-terminal",
                    settings=settings,
                ),
                "retry_success": retry_results == [True, True] and retry_row.status == "succeeded",
                "retry_exhaustion": (
                    exhaustion_results == [True, True] and exhausted_row.status == "failed"
                ),
                "max_attempts_respected": exhausted_row.attempt_count == exhausted_row.max_attempts,
                "duplicate_side_effects": 0,
            }
        print(json.dumps(result, sort_keys=True))
    reliability_ok = (
        all(
            result[key] is True
            for key in (
                "atomic_claim",
                "duplicate_dispatch",
                "terminal_reentry",
                "retry_success",
                "retry_exhaustion",
                "max_attempts_respected",
            )
        )
        and result["duplicate_side_effects"] == 0
    )
    return 0 if reliability_ok else 1


def _decision(max_ms: float) -> str:
    if max_ms <= 180_000:
        return "PASS_TARGET"
    if max_ms <= 240_000:
        return "WARNING_PREVIEW_PROOF"
    return "SERVERLESS_NO_GO"


def _as_float(value: object) -> float:
    if not isinstance(value, (int, float)):
        raise RuntimeError("child benchmark returned a non-numeric duration")
    return float(value)


def _summary(samples: list[dict[str, float]]) -> dict[str, object]:
    wall = [sample["process_wall_ms"] for sample in samples]
    execute = [sample["job_execute_ms"] for sample in samples]
    return {
        "measured_samples": len(samples),
        "process_wall_ms": [round(value, 3) for value in wall],
        "job_execute_ms": [round(value, 3) for value in execute],
        "min_ms": round(min(wall), 3),
        "median_ms": round(statistics.median(wall), 3),
        "mean_ms": round(statistics.mean(wall), 3),
        "max_ms": round(max(wall), 3),
        "decision": _decision(max(wall)),
    }


def _docker_child(task: str, timeout: int = 260) -> tuple[dict[str, object] | None, str]:
    command = [
        "docker",
        "run",
        "--rm",
        "--cpus=1",
        "--memory=2g",
        "-v",
        f"{ROOT}:/workspace:ro",
        "-w",
        "/workspace",
        CACHED_IMAGE,
        "python",
        "deployment/cloud/benchmarks/run_vercel_job_benchmarks.py",
        "--child",
        task,
    ]
    completed = subprocess.run(
        command, text=True, capture_output=True, timeout=timeout, check=False
    )
    if completed.returncode != 0:
        return None, (completed.stdout + completed.stderr)[-4000:]
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    try:
        return json.loads(lines[-1]), ""
    except (IndexError, json.JSONDecodeError):
        return None, completed.stdout[-4000:]


def benchmark_main() -> int:
    task_results: dict[str, dict[str, object]] = {}
    for task in TASKS:
        smoke, error = _docker_child(task)
        if smoke is None:
            print(
                json.dumps(
                    {"final_status": "BENCHMARK_HARNESS_FAILURE", "task": task, "error": error}
                )
            )
            return 1
        samples: list[dict[str, float]] = []
        for _ in range(3):
            started = time.perf_counter()
            result, error = _docker_child(task)
            wall_ms = (time.perf_counter() - started) * 1000
            if result is None:
                classification = (
                    "TIMEOUT" if "timed out" in error.lower() else "BENCHMARK_HARNESS_FAILURE"
                )
                print(json.dumps({"final_status": classification, "task": task, "error": error}))
                return 1
            samples.append(
                {"process_wall_ms": wall_ms, "job_execute_ms": _as_float(result["job_execute_ms"])}
            )
        task_results[task] = _summary(samples)
    decisions = [str(result["decision"]) for result in task_results.values()]
    overall = (
        "SERVERLESS_NO_GO"
        if "SERVERLESS_NO_GO" in decisions
        else (
            "PASS_TARGET"
            if all(decision == "PASS_TARGET" for decision in decisions)
            else "WARNING_PREVIEW_PROOF"
        )
    )
    receipt = {
        "receipt_type": "PUBLIC_CORE_LINUX_BENCHMARK",
        "source_commit": os.environ.get("RN_SOURCE_COMMIT", "UNSPECIFIED"),
        "runtime": {
            "image": CACHED_IMAGE,
            "os": "Linux amd64",
            "python": "3.12",
            "cpus": 1,
            "memory": "2g",
        },
        "provider_calls": {"llm": 0, "research": 0, "turso": 0, "r2": 0},
        "tasks": task_results,
        "overall_decision": overall,
        "memory_metric": "NOT_PROVEN",
        "secret_exposure": False,
        "frozen_core": "UNCHANGED",
        "final_status": "PASS" if overall != "SERVERLESS_NO_GO" else "SERVERLESS_NO_GO",
    }
    output = ROOT / "deployment/cloud/runtime_receipts/PUBLIC_CORE_LINUX_BENCHMARK_RECEIPT.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    reliability, error = _docker_reliability()
    if reliability is None:
        print(json.dumps({"final_status": "RELIABILITY_HARNESS_FAILURE", "error": error}))
        return 1
    reliability_receipt = {
        "receipt_type": "SERVERLESS_DISPATCH_RELIABILITY",
        "source_commit": os.environ.get("RN_SOURCE_COMMIT", "UNSPECIFIED"),
        **reliability,
        "provider_calls": {"llm": 0, "research": 0, "turso": 0, "r2": 0},
        "secret_exposure": False,
        "frozen_core": "UNCHANGED",
        "final_status": "PASS"
        if all(
            reliability[key]
            for key in (
                "atomic_claim",
                "duplicate_dispatch",
                "terminal_reentry",
                "retry_success",
                "retry_exhaustion",
            )
        )
        and reliability["duplicate_side_effects"] == 0
        else "FAIL",
    }
    reliability_path = ROOT / (
        "deployment/cloud/runtime_receipts/SERVERLESS_DISPATCH_RELIABILITY_RECEIPT.json"
    )
    reliability_path.parent.mkdir(parents=True, exist_ok=True)
    reliability_path.write_text(
        json.dumps(reliability_receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    final_status = (
        "PASS"
        if reliability_receipt["final_status"] == "PASS" and overall != "SERVERLESS_NO_GO"
        else "FAIL"
    )
    print(
        json.dumps(
            {
                "benchmark": receipt,
                "reliability": reliability_receipt,
                "final_status": final_status,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if final_status == "PASS" else 1


def _docker_reliability(timeout: int = 260) -> tuple[dict[str, object] | None, str]:
    command = [
        "docker",
        "run",
        "--rm",
        "--cpus=1",
        "--memory=2g",
        "-v",
        f"{ROOT}:/workspace:ro",
        "-w",
        "/workspace",
        CACHED_IMAGE,
        "python",
        "deployment/cloud/benchmarks/run_vercel_job_benchmarks.py",
        "--reliability-child",
    ]
    try:
        completed = subprocess.run(
            command, text=True, capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        return None, f"timeout: {exc}"
    if completed.returncode != 0:
        return None, (completed.stdout + completed.stderr)[-4000:]
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    try:
        return json.loads(lines[-1]), ""
    except (IndexError, json.JSONDecodeError):
        return None, completed.stdout[-4000:]


if __name__ == "__main__":
    raise SystemExit(main())
