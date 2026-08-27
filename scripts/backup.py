#!/usr/bin/env python3
"""Create a consistent, integrity-described backup of SQLite, uploads, and vector state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, default=Path("runtime"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    database = runtime / "research_navigator.db"
    if not database.is_file():
        raise SystemExit(f"Database not found: {database}")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output or runtime / "backups" / f"research-navigator-{timestamp}.zip").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="rn-backup-cli-") as temp_dir:
        snapshot = Path(temp_dir) / "research_navigator.db"
        with sqlite3.connect(database) as source, sqlite3.connect(snapshot) as target:
            source.backup(target)
        with sqlite3.connect(snapshot) as check:
            integrity = check.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise SystemExit("SQLite snapshot integrity check failed")

        files: list[tuple[Path, str]] = [(snapshot, "research_navigator.db")]
        for directory in ("uploads", "vector_index"):
            root = runtime / directory
            if root.exists():
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        files.append((path, path.relative_to(runtime).as_posix()))

        manifest = {
            "format_version": 2,
            "created_at": datetime.now(UTC).isoformat(),
            "database_filename": database.name,
            "source_runtime": str(runtime),
            "files": [
                {"path": archive_name, "size_bytes": path.stat().st_size, "sha256": sha256(path)}
                for path, archive_name in files
            ],
        }
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            for path, archive_name in files:
                archive.write(path, archive_name)
            archive.writestr(
                "backup-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
            )
    print(output)


if __name__ == "__main__":
    main()
