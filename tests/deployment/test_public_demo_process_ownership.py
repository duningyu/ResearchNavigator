import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INSPECT_SCRIPT = (
    PROJECT_ROOT / "scripts" / "deployment" / "inspect_process_ownership.ps1"
)


def process(
    pid: int,
    parent_pid: int,
    created: str,
    *,
    name: str = "fixture.exe",
) -> dict[str, object]:
    return {
        "process_id": pid,
        "parent_process_id": parent_pid,
        "creation_time_utc": created,
        "name": name,
        "executable_path": f"C:/fixture/{name}",
        "command_line": f"{name} --fixture-pid {pid}",
    }


def inspect(
    tmp_path: Path,
    snapshot: list[dict[str, object]],
    *,
    root_pid: int = 500,
    root_creation: str = "2026-08-31T10:30:00Z",
) -> subprocess.CompletedProcess[str]:
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    return subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(INSPECT_SCRIPT),
            "-SnapshotPath",
            str(snapshot_path),
            "-RootPid",
            str(root_pid),
            "-RootCreationTimeUtc",
            root_creation,
            "-SnapshotTimeUtc",
            "2026-08-31T10:31:00Z",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    return json.loads(result.stdout)


def test_older_process_with_reused_parent_pid_is_not_descendant(tmp_path: Path) -> None:
    result = payload(
        inspect(
            tmp_path,
            [
                process(500, 10, "2026-08-31T10:30:00Z", name="cloudflared.exe"),
                process(600, 500, "2026-08-31T09:59:00Z", name="python.exe"),
                process(601, 500, "2026-08-31T10:00:00Z", name="python.exe"),
            ],
        )
    )
    assert [item["pid"] for item in result["accepted_tree"]] == [500]
    assert {(item["child_pid"], item["reason"]) for item in result["rejected_edges"]} == {
        (600, "IMPOSSIBLE_CAUSAL_PARENT_EDGE"),
        (601, "IMPOSSIBLE_CAUSAL_PARENT_EDGE"),
    }


def test_valid_causal_child_and_grandchild_are_descendants(tmp_path: Path) -> None:
    result = payload(
        inspect(
            tmp_path,
            [
                process(500, 10, "2026-08-31T10:30:00Z"),
                process(600, 500, "2026-08-31T10:30:01Z"),
                process(601, 600, "2026-08-31T10:30:02Z"),
            ],
        )
    )
    assert [item["pid"] for item in result["accepted_tree"]] == [500, 600, 601]
    assert result["rejected_edges"] == []


def test_same_pid_with_different_creation_time_is_pid_reused(tmp_path: Path) -> None:
    result = payload(
        inspect(
            tmp_path,
            [process(700, 10, "2026-08-31T11:00:00Z")],
            root_pid=700,
            root_creation="2026-08-31T10:00:00Z",
        )
    )
    assert result["root_trusted"] is False
    assert result["classification"] == "PID_REUSED"
    assert result["accepted_tree"] == []


def test_mixed_tree_does_not_traverse_through_invalid_edge(tmp_path: Path) -> None:
    result = payload(
        inspect(
            tmp_path,
            [
                process(500, 10, "2026-08-31T10:30:00Z"),
                process(600, 500, "2026-08-31T10:30:01Z"),
                process(602, 600, "2026-08-31T10:30:02Z"),
                process(601, 500, "2026-08-31T10:00:00Z"),
                process(603, 601, "2026-08-31T10:30:03Z"),
            ],
        )
    )
    assert [item["pid"] for item in result["accepted_tree"]] == [500, 600, 602]
    assert [item["child_pid"] for item in result["rejected_edges"]] == [601]
    assert 603 not in [item["pid"] for item in result["accepted_tree"]]
