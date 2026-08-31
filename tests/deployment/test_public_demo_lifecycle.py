import json
import socket
import subprocess
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
START_SCRIPT = PROJECT_ROOT / "scripts" / "deployment" / "start_public_demo.ps1"
STOP_SCRIPT = PROJECT_ROOT / "scripts" / "deployment" / "stop_public_demo.ps1"
STATUS_SCRIPT = PROJECT_ROOT / "scripts" / "deployment" / "status_public_demo.ps1"
RESTART_SCRIPT = PROJECT_ROOT / "scripts" / "deployment" / "restart_public_demo_component.ps1"


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def run_script(
    script: Path, arguments: list[str], timeout: int = 180
) -> subprocess.CompletedProcess[str]:
    command = [
        "pwsh",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *arguments,
    ]
    state_path = Path(arguments[arguments.index("-StatePath") + 1])
    log_dir = state_path.parent / "command-logs"
    log_dir.mkdir(exist_ok=True)
    command_id = uuid.uuid4().hex
    stdout_path = log_dir / f"{command_id}-stdout.log"
    stderr_path = log_dir / f"{command_id}-stderr.log"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        result = subprocess.run(
            command,
            stdout=stdout,
            stderr=stderr,
            timeout=timeout,
            check=False,
        )
    return subprocess.CompletedProcess(
        command,
        result.returncode,
        stdout_path.read_text(encoding="utf-8", errors="replace"),
        stderr_path.read_text(encoding="utf-8", errors="replace"),
    )


def start_arguments(
    data_dir: Path, state_path: Path, fake_cloudflared: Path, port: int
) -> list[str]:
    return [
        "-ProjectRoot",
        str(PROJECT_ROOT),
        "-VercelOrigin",
        "https://rn223-public-demo.vercel.app/",
        "-ApiPort",
        str(port),
        "-DemoDataDir",
        str(data_dir),
        "-StatePath",
        str(state_path),
        "-CloudflaredPath",
        sys.executable,
        "-CloudflaredArgumentPrefix",
        str(fake_cloudflared),
        "-PythonPath",
        sys.executable,
    ]


def stop_arguments(state_path: Path) -> list[str]:
    return ["-ProjectRoot", str(PROJECT_ROOT), "-StatePath", str(state_path)]


def status_arguments(state_path: Path, output_path: Path) -> list[str]:
    return [
        "-ProjectRoot",
        str(PROJECT_ROOT),
        "-StatePath",
        str(state_path),
        "-PythonPath",
        sys.executable,
        "-EmitJson",
        "-OutputPath",
        str(output_path),
        "-SkipExternalChecks",
    ]


def restart_arguments(state_path: Path, component: str) -> list[str]:
    return [
        "-ProjectRoot",
        str(PROJECT_ROOT),
        "-StatePath",
        str(state_path),
        "-PythonPath",
        sys.executable,
        "-Component",
        component,
    ]


def write_fake_cloudflared(path: Path) -> None:
    path.write_text(
        "import sys\n"
        "import time\n"
        "print('INF fake quick tunnel https://fixture-demo.trycloudflare.com', "
        "file=sys.stderr, flush=True)\n"
        "time.sleep(300)\n",
        encoding="utf-8",
    )


def process_alive(pid: int) -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return f'"{pid}"' in result.stdout


def test_start_is_idempotent_stop_is_owned_and_stale_state_recovers(tmp_path: Path) -> None:
    data_dir = tmp_path / "ResearchNavigatorPublicDemo"
    state_path = tmp_path / "public_demo_state.json"
    fake_cloudflared = tmp_path / "fake_cloudflared.py"
    write_fake_cloudflared(fake_cloudflared)
    port = free_port()
    sentinel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    try:
        first = run_script(
            START_SCRIPT, start_arguments(data_dir, state_path, fake_cloudflared, port)
        )
        assert first.returncode == 0, f"{first.stdout}\n{first.stderr}"
        first_state = json.loads(state_path.read_text(encoding="utf-8-sig"))

        second = run_script(
            START_SCRIPT, start_arguments(data_dir, state_path, fake_cloudflared, port)
        )
        assert second.returncode == 0, f"{second.stdout}\n{second.stderr}"
        second_state = json.loads(state_path.read_text(encoding="utf-8-sig"))
        for key in ("api_pid", "worker_pid", "cloudflared_pid", "started_at"):
            assert second_state[key] == first_state[key]

        status_path = tmp_path / "public_demo_status.json"
        running_status = run_script(STATUS_SCRIPT, status_arguments(state_path, status_path))
        assert running_status.returncode == 0, f"{running_status.stdout}\n{running_status.stderr}"
        status_payload = json.loads(status_path.read_text(encoding="utf-8-sig"))
        assert status_payload["status"] == "DEGRADED"
        assert status_payload["components"]["local_api"] == "ONLINE"
        assert status_payload["components"]["worker"] == "ONLINE"
        assert status_payload["components"]["cloudflared"] == "ONLINE"
        assert status_payload["database"]["integrity_check"] == "ok"

        worker_restart = run_script(RESTART_SCRIPT, restart_arguments(state_path, "Worker"))
        assert worker_restart.returncode == 0, worker_restart.stdout + worker_restart.stderr
        after_worker = json.loads(state_path.read_text(encoding="utf-8-sig"))
        assert after_worker["worker_pid"] != second_state["worker_pid"]
        assert after_worker["api_pid"] == second_state["api_pid"]
        assert after_worker["cloudflared_pid"] == second_state["cloudflared_pid"]

        api_restart = run_script(RESTART_SCRIPT, restart_arguments(state_path, "Api"))
        assert api_restart.returncode == 0, api_restart.stdout + api_restart.stderr
        after_api = json.loads(state_path.read_text(encoding="utf-8-sig"))
        assert after_api["api_pid"] != after_worker["api_pid"]
        assert after_api["worker_pid"] == after_worker["worker_pid"]
        assert after_api["cloudflared_pid"] == after_worker["cloudflared_pid"]

        stopped = run_script(STOP_SCRIPT, stop_arguments(state_path))
        assert stopped.returncode == 0, f"{stopped.stdout}\n{stopped.stderr}"
        assert not state_path.exists()
        assert sentinel.poll() is None
        for key in ("api_pid", "worker_pid", "cloudflared_pid"):
            assert not process_alive(int(first_state[key]))
        stopped_status = run_script(STATUS_SCRIPT, status_arguments(state_path, status_path))
        assert stopped_status.returncode == 0
        assert json.loads(status_path.read_text(encoding="utf-8-sig"))["status"] == "OFFLINE"

        state_path.write_text(json.dumps(first_state), encoding="utf-8")
        recovered = run_script(
            START_SCRIPT, start_arguments(data_dir, state_path, fake_cloudflared, port)
        )
        assert recovered.returncode == 0, f"{recovered.stdout}\n{recovered.stderr}"
        recovered_state = json.loads(state_path.read_text(encoding="utf-8-sig"))
        assert recovered_state["started_at"] != first_state["started_at"]
        assert process_alive(int(recovered_state["api_pid"]))
        assert process_alive(int(recovered_state["worker_pid"]))
        assert process_alive(int(recovered_state["cloudflared_pid"]))
        assert sentinel.poll() is None
    finally:
        run_script(STOP_SCRIPT, stop_arguments(state_path), timeout=60)
        if sentinel.poll() is None:
            sentinel.terminate()
            sentinel.wait(timeout=10)
