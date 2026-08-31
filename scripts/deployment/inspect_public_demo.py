"""Read bounded, non-secret status from an isolated public demo runtime."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def inspect(data_dir: Path) -> dict[str, Any]:
    database = data_dir / "research_navigator.db"
    result: dict[str, Any] = {
        "path": str(database),
        "exists": database.is_file(),
        "size_bytes": database.stat().st_size if database.is_file() else 0,
        "uploads_size_bytes": directory_size(data_dir / "uploads"),
        "active_jobs": None,
        "integrity_check": "not_available",
    }
    if not database.is_file():
        return result
    try:
        with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
            result["integrity_check"] = connection.execute("PRAGMA integrity_check").fetchone()[0]
            jobs_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'"
            ).fetchone()
            if jobs_table:
                result["active_jobs"] = connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status IN ('pending', 'running')"
                ).fetchone()[0]
    except sqlite3.Error as exc:
        result["integrity_check"] = f"error:{type(exc).__name__}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.data_dir.resolve()), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
