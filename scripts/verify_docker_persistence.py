#!/usr/bin/env python3
"""Cold-start, restart, down/up, backup/restore acceptance for Docker Compose.

The harness deliberately uses a dedicated bind-mounted runtime directory and an
isolated Compose project. User-owned scenario state is created through HTTP.
The only direct database write is the acceptance-only bootstrap that promotes
the newly registered user to administrator so the public backup API can be
exercised.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "infra" / "docker-compose.acceptance.yml"
PROJECT_NAME = "rn-acceptance"
TERMINAL_JOB_STATES = {"succeeded", "partial", "failed", "cancelled"}


class AcceptanceFailure(RuntimeError):
    """A deterministic acceptance assertion failed."""


@dataclass(slots=True)
class HttpClient:
    base_url: str
    token: str | None = None
    timeout: float = 30.0

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | list[Any] | None = None,
        headers: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        request_headers = {"Accept": "application/json", **(headers or {})}
        if self.token:
            request_headers["Authorization"] = f"Bearer {self.token}"
        data: bytes | None = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/{path.lstrip('/')}",
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                status = int(response.status)
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            body = exc.read()
            detail = body.decode("utf-8", errors="replace")
            raise AcceptanceFailure(
                f"HTTP {method} {path} returned {exc.code}, expected {expected}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise AcceptanceFailure(f"HTTP {method} {path} failed: {exc}") from exc
        if status not in expected:
            raise AcceptanceFailure(
                f"HTTP {method} {path} returned {status}, expected {expected}"
            )
        if not body:
            return None
        if "application/json" in content_type:
            return json.loads(body)
        return body

    def upload_pdf(self, paper_id: int, pdf: bytes) -> dict[str, Any]:
        boundary = f"----rn-acceptance-{uuid.uuid4().hex}"
        chunks: list[bytes] = []

        def field(name: str, value: str) -> None:
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                    value.encode(),
                    b"\r\n",
                ]
            )

        field("rights_confirmed", "true")
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="file"; filename="acceptance.pdf"\r\n',
                b"Content-Type: application/pdf\r\n\r\n",
                pdf,
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
        )
        data = b"".join(chunks)
        headers = {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(data)),
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/papers/{paper_id}/upload",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AcceptanceFailure(f"PDF upload returned {exc.code}: {detail}") from exc
        if status not in {200, 201}:
            raise AcceptanceFailure(f"PDF upload returned {status}")
        return json.loads(body)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_text_pdf(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, value in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode())
        output.extend(value)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def runtime_sha256(runtime_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(runtime_dir.rglob("*")):
        if not path.is_file() or path.name.endswith(("-wal", "-shm")):
            continue
        relative = path.relative_to(runtime_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def database_snapshot(database_path: Path) -> dict[str, Any]:
    if not database_path.is_file():
        raise AcceptanceFailure(f"SQLite database is missing: {database_path}")
    with sqlite3.connect(database_path) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise AcceptanceFailure(f"PRAGMA integrity_check failed: {integrity}")
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        counts: dict[str, int] = {}
        for table in (
            "users",
            "research_projects",
            "papers",
            "favorites",
            "paper_documents",
            "paper_chunks",
            "paper_analysis_records",
            "jobs",
            "job_events",
        ):
            if table in tables:
                counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        return {"integrity": "ok", "counts": counts}


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_command(
    command: list[str],
    *,
    environment: dict[str, str],
    report: dict[str, Any],
    timeout: float = 900.0,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    report.setdefault("commands", []).append(
        {
            "command": command,
            "returncode": completed.returncode,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
        }
    )
    if check and completed.returncode != 0:
        raise AcceptanceFailure(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n{completed.stderr[-2000:]}"
        )
    return completed


def wait_for_health(client: HttpClient, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            health = client.request("GET", "/health")
            if health.get("database") == "ok":
                return health
            last_error = json.dumps(health, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001 - diagnostic loop
            last_error = str(exc)
        time.sleep(1)
    raise AcceptanceFailure(f"API health did not become ready: {last_error}")


def promote_admin(database_path: Path, email: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with sqlite3.connect(database_path, timeout=5) as connection:
                changed = connection.execute(
                    "UPDATE users SET is_admin = 1 WHERE email = ?", (email,)
                ).rowcount
                connection.commit()
            if changed == 1:
                return
        except sqlite3.Error:
            pass
        time.sleep(0.5)
    raise AcceptanceFailure("Acceptance user could not be promoted to administrator")


def seed_http_scenario(client: HttpClient, runtime_dir: Path) -> dict[str, Any]:
    unique = uuid.uuid4().hex
    email = f"docker-acceptance-{unique}@example.com"
    password = "Docker-Acceptance-Password-123!"
    registration = client.request(
        "POST",
        "/auth/register",
        payload={"email": email, "password": password, "display_name": "Docker Acceptance"},
        expected=(201,),
    )
    client.token = str(registration["access_token"])
    promote_admin(runtime_dir / "research_navigator.db", email)
    me = client.request("GET", "/auth/me")
    if not me.get("is_admin"):
        raise AcceptanceFailure("Admin bootstrap did not take effect")

    project = client.request(
        "POST",
        "/projects",
        headers={"Idempotency-Key": f"docker-project-{unique}"},
        payload={
            "name": f"Docker persistence {unique[:8]}",
            "description": "HTTP-first restart persistence acceptance",
            "broad_direction": "time-series anomaly detection",
        },
        expected=(201,),
    )
    search = client.request(
        "POST",
        "/search/papers",
        payload={
            "query": "industrial time series anomaly detection",
            "limit": 2,
            "sources": ["fixture"],
            "project_id": int(project["id"]),
            "mode": "precise",
        },
    )
    if not search.get("papers"):
        raise AcceptanceFailure("Fixture search returned no papers")
    paper = search["papers"][0]
    paper_id = int(paper["id"])
    favorite = client.request(
        "POST",
        "/library/favorites",
        headers={"Idempotency-Key": f"docker-favorite-{unique}"},
        payload={"paper_id": paper_id},
        expected=(201,),
    )
    pdf = build_text_pdf(
        "ResearchNavigator Docker persistence evidence. Dataset: acceptance fixture. "
        "Method: deterministic anomaly detection. Metric: precision recall."
    )
    document = client.upload_pdf(paper_id, pdf)
    analysis = client.request(
        "POST",
        f"/papers/{paper_id}/analyze",
        payload={"project_id": int(project["id"]), "provider": "deterministic"},
    )
    workflow = client.request(
        "POST",
        f"/papers/{paper_id}/evidence-workflows",
        payload={
            "project_id": int(project["id"]),
            "sources": ["fixture"],
            "allow_oa_fulltext": False,
            "confirm_limited_license": False,
        },
        expected=(201,),
    )
    workflow_id = int(workflow["id"])
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        workflow = client.request("GET", f"/evidence-workflows/{workflow_id}")
        if workflow["status"] in TERMINAL_JOB_STATES:
            break
        time.sleep(1)
    if workflow["status"] not in {"succeeded", "partial"}:
        raise AcceptanceFailure(f"Worker did not complete evidence workflow: {workflow}")
    return {
        "email": email,
        "password": password,
        "token": client.token,
        "project_id": int(project["id"]),
        "project_name": str(project["name"]),
        "paper_id": paper_id,
        "favorite_id": int(favorite["id"]),
        "document_id": int(document["id"]),
        "document_sha256": str(document["sha256"]),
        "analysis_id": int(analysis["id"]),
        "workflow_id": workflow_id,
        "workflow_status": str(workflow["status"]),
        "pdf_sha256": sha256_bytes(pdf),
    }


def verify_http_scenario(client: HttpClient, state: dict[str, Any]) -> dict[str, Any]:
    me = client.request("GET", "/auth/me")
    projects = client.request("GET", "/projects")
    library = client.request("GET", "/library")
    documents = client.request("GET", f"/papers/{state['paper_id']}/documents")
    analysis = client.request("GET", f"/papers/{state['paper_id']}/analysis")
    workflow = client.request("GET", f"/evidence-workflows/{state['workflow_id']}")
    if not any(int(row["id"]) == state["project_id"] for row in projects):
        raise AcceptanceFailure("Project disappeared after lifecycle transition")
    if not any(int(item["paper"]["id"]) == state["paper_id"] and item["favorite"] for item in library["items"]):
        raise AcceptanceFailure("Favorite disappeared after lifecycle transition")
    document = next((row for row in documents if int(row["id"]) == state["document_id"]), None)
    if document is None or document["sha256"] != state["document_sha256"]:
        raise AcceptanceFailure("PDF document/hash disappeared after lifecycle transition")
    if int(analysis["id"]) < state["analysis_id"]:
        raise AcceptanceFailure("Latest analysis regressed to an older record")
    if workflow["status"] not in {"succeeded", "partial"}:
        raise AcceptanceFailure(f"Workflow is not terminal after lifecycle transition: {workflow['status']}")
    return {
        "user_id": int(me["id"]),
        "project_count": len(projects),
        "library_items": len(library["items"]),
        "document_count": len(documents),
        "latest_analysis_id": int(analysis["id"]),
        "workflow_status": workflow["status"],
        "workflow_event_count": len(workflow["events"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker-executable", default="docker")
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=ROOT / "codex_audit" / "runtime" / "docker-acceptance",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "codex_audit" / "DOCKER_PERSISTENCE_REPORT.json",
    )
    parser.add_argument("--api-port", type=int, default=18000)
    parser.add_argument("--web-port", type=int, default=18080)
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    parser.add_argument("--keep-running", action="store_true")
    args = parser.parse_args(argv)

    runtime_dir = args.runtime_dir.expanduser().resolve()
    output = args.output.expanduser().resolve()
    report: dict[str, Any] = {
        "schema_version": 1,
        "started_at": utc_now(),
        "status": "RUNNING",
        "compose_project": PROJECT_NAME,
        "compose_file": str(COMPOSE_FILE),
        "runtime_dir": str(runtime_dir),
        "phases": {},
        "commands": [],
    }
    write_report(output, report)

    executable = shutil.which(args.docker_executable)
    if executable is None:
        report["status"] = "BLOCKED"
        report["finished_at"] = utc_now()
        report["phases"]["docker_available"] = {
            "status": "BLOCKED",
            "reason": f"Docker executable not found: {args.docker_executable}",
        }
        write_report(output, report)
        return 2

    environment = dict(os.environ)
    environment.update(
        {
            "RN_ACCEPTANCE_RUNTIME_DIR": str(runtime_dir),
            "RN_ACCEPTANCE_API_PORT": str(args.api_port),
            "RN_ACCEPTANCE_WEB_PORT": str(args.web_port),
        }
    )
    compose = [
        executable,
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "-p",
        PROJECT_NAME,
    ]
    client = HttpClient(f"http://127.0.0.1:{args.api_port}/api")
    services_started = False

    try:
        run_command([executable, "compose", "version"], environment=environment, report=report, timeout=30)
        report["phases"]["docker_available"] = {"status": "PASS", "executable": executable}

        marker = runtime_dir / ".rn-acceptance-runtime"
        if runtime_dir.exists() and any(runtime_dir.iterdir()) and not marker.exists():
            raise AcceptanceFailure(
                f"Refusing to reset non-empty unmarked runtime directory: {runtime_dir}"
            )
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir)
        runtime_dir.mkdir(parents=True)
        marker.write_text("ResearchNavigator dedicated Docker acceptance runtime\n", encoding="utf-8")
        report["phases"]["runtime_prepared"] = {"status": "PASS"}

        run_command(compose + ["down", "--remove-orphans"], environment=environment, report=report, check=False)
        run_command(compose + ["build", "--no-cache"], environment=environment, report=report)
        report["phases"]["build"] = {"status": "PASS", "no_cache": True}

        run_command(compose + ["up", "-d", "--wait"], environment=environment, report=report, timeout=args.timeout_seconds)
        services_started = True
        health = wait_for_health(client, args.timeout_seconds)
        report["phases"]["cold_start"] = {"status": "PASS", "health": health}

        state = seed_http_scenario(client, runtime_dir)
        report["scenario"] = {key: value for key, value in state.items() if key not in {"token", "password"}}
        report["phases"]["http_seed"] = {"status": "PASS", "worker_terminal": state["workflow_status"]}
        first_verify = verify_http_scenario(client, state)
        report["phases"]["initial_state"] = {"status": "PASS", **first_verify}

        run_command(compose + ["restart", "api", "worker"], environment=environment, report=report, timeout=args.timeout_seconds)
        wait_for_health(client, args.timeout_seconds)
        after_restart = verify_http_scenario(client, state)
        report["phases"]["service_restart"] = {"status": "PASS", **after_restart}

        run_command(compose + ["down", "--remove-orphans"], environment=environment, report=report)
        services_started = False
        run_command(compose + ["up", "-d", "--wait"], environment=environment, report=report, timeout=args.timeout_seconds)
        services_started = True
        wait_for_health(client, args.timeout_seconds)
        after_down_up = verify_http_scenario(client, state)
        report["phases"]["down_up"] = {"status": "PASS", **after_down_up}

        backup = client.request("POST", "/admin/backups", expected=(201,))
        report["phases"]["backup"] = {
            "status": "PASS",
            "name": backup["name"],
            "sha256": backup["sha256"],
        }
        mutation = client.request(
            "POST",
            "/projects",
            headers={"Idempotency-Key": f"restore-mutation-{uuid.uuid4().hex}"},
            payload={"name": f"restore-mutation-{uuid.uuid4().hex[:8]}"},
            expected=(201,),
        )
        run_command(compose + ["stop", "worker"], environment=environment, report=report)
        staged = client.request(
            "POST",
            f"/admin/backups/{urllib.parse.quote(str(backup['name']))}/stage-restore",
            payload={"confirm_restore": True},
            expected=(202,),
        )
        if not staged.get("restart_required"):
            raise AcceptanceFailure("stage-restore did not require restart")
        run_command(compose + ["restart", "api"], environment=environment, report=report, timeout=args.timeout_seconds)
        wait_for_health(client, args.timeout_seconds)
        run_command(compose + ["start", "worker"], environment=environment, report=report)
        after_restore = verify_http_scenario(client, state)
        projects_after_restore = client.request("GET", "/projects")
        if any(int(row["id"]) == int(mutation["id"]) for row in projects_after_restore):
            raise AcceptanceFailure("Staged restore did not remove post-backup mutation")
        report["phases"]["backup_restore"] = {"status": "PASS", **after_restore}

        run_command(compose + ["down", "--remove-orphans"], environment=environment, report=report)
        services_started = False
        database = database_snapshot(runtime_dir / "research_navigator.db")
        stored_pdf = runtime_dir / "uploads" / str(after_restore["user_id"]) / str(state["paper_id"]) / f"{state['document_sha256']}.pdf"
        if not stored_pdf.is_file() or sha256_file(stored_pdf) != state["document_sha256"]:
            raise AcceptanceFailure("Persisted PDF is missing or hash-mismatched")
        report["phases"]["filesystem_database"] = {
            "status": "PASS",
            "database": database,
            "pdf_sha256": sha256_file(stored_pdf),
            "runtime_sha256": runtime_sha256(runtime_dir),
        }
        report["status"] = "PASS"
        report["finished_at"] = utc_now()
        write_report(output, report)
        return 0
    except (AcceptanceFailure, subprocess.TimeoutExpired, OSError, ValueError) as exc:
        report["status"] = "FAIL"
        report["finished_at"] = utc_now()
        report["failure"] = f"{type(exc).__name__}: {exc}"
        try:
            logs = run_command(
                compose + ["logs", "--no-color", "--tail", "200"],
                environment=environment,
                report=report,
                timeout=60,
                check=False,
            )
            report["logs_tail"] = (logs.stdout + "\n" + logs.stderr)[-12000:]
        except Exception as log_exc:  # noqa: BLE001 - best-effort failure evidence
            report["logs_error"] = str(log_exc)
        write_report(output, report)
        return 1
    finally:
        if services_started and not args.keep_running:
            try:
                run_command(
                    compose + ["down", "--remove-orphans"],
                    environment=environment,
                    report=report,
                    timeout=120,
                    check=False,
                )
                write_report(output, report)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
