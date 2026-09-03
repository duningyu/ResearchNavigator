"""Run bounded local executor benchmarks without live provider traffic.

This harness deliberately reports fixture-suite timing separately from isolated
job timing. It is evidence for engineering progress, not a Vercel GO decision;
real Preview runs remain mandatory under the frozen contract.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGETS = [
    "tests/integration/test_worker_claim.py",
    "tests/integration/test_worker_handlers.py",
    "tests/integration/test_worker_evidence_workflow.py",
    "tests/integration/test_gap_workflow.py",
]


def main() -> int:
    command = [sys.executable, "-m", "pytest", *TARGETS, "-q"]
    start = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "RN_DISABLE_LIVE_PROVIDER": "1"},
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed = time.perf_counter() - start
    result = {
        "receipt_type": "VERCEL_JOB_BENCHMARK",
        "mode": "local_fixture_no_live_provider",
        "suite": TARGETS,
        "sample_count": "pytest_cases_not_isolated_jobs",
        "exit_code": completed.returncode,
        "wall_time_seconds": round(elapsed, 3),
        "peak_rss": "NOT_MEASURED",
        "external_request_count": 0,
        "per_job_runtime": "NOT_MEASURED_BY_THIS_HARNESS",
        "interpretation": "fixture-suite smoke evidence only; Preview benchmark required",
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
