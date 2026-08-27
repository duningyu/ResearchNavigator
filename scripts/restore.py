#!/usr/bin/env python3
"""Validate then restore a ResearchNavigator backup into a stopped runtime directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from zipfile import BadZipFile, ZipFile


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_backup(backup: Path, staging: Path) -> dict[str, object]:
    """Extract into an isolated directory and verify paths, manifest, hashes and SQLite."""
    backup = backup.resolve()
    staging = staging.resolve()
    staging.mkdir(parents=True, exist_ok=True)
    try:
        with ZipFile(backup) as archive:
            names = {member.filename for member in archive.infolist()}
            if "research_navigator.db" not in names or "backup-manifest.json" not in names:
                raise ValueError("Backup is missing research_navigator.db or backup-manifest.json")
            for member in archive.infolist():
                target = (staging / member.filename).resolve()
                if staging not in target.parents and target != staging:
                    raise ValueError(f"Unsafe archive path: {member.filename}")
            archive.extractall(staging)
    except BadZipFile as exc:
        raise ValueError("Backup is not a valid ZIP archive") from exc

    try:
        manifest = json.loads((staging / "backup-manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Backup manifest is invalid") from exc
    if int(manifest.get("format_version", 0)) not in {1, 2}:
        raise ValueError("Unsupported backup format version")

    for entry in manifest.get("files", []):
        relative = Path(str(entry.get("path", "")))
        target = (staging / relative).resolve()
        if staging not in target.parents or not target.is_file():
            raise ValueError(f"Manifest file is missing or unsafe: {relative.as_posix()}")
        expected = entry.get("sha256")
        if expected and sha256(target) != expected:
            raise ValueError(f"Backup checksum mismatch: {relative.as_posix()}")

    try:
        with sqlite3.connect(staging / "research_navigator.db") as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError as exc:
        raise ValueError("SQLite backup integrity check failed") from exc
    if not integrity or integrity[0] != "ok":
        raise ValueError("SQLite backup integrity check failed")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    parser.add_argument("--runtime", type=Path, default=Path("runtime"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    backup = args.backup.resolve()
    runtime = args.runtime.resolve()
    if not backup.is_file():
        raise SystemExit(f"Backup not found: {backup}")
    database = runtime / "research_navigator.db"
    if database.exists() and not args.force:
        raise SystemExit(
            "Destination database exists. Stop services and pass --force to replace it."
        )

    with tempfile.TemporaryDirectory(prefix="rn-restore-cli-") as temp_dir:
        staging = Path(temp_dir) / "validated"
        validate_backup(backup, staging)

        # Destructive replacement begins only after the complete archive has validated.
        if args.force and runtime.exists():
            for item in (database, runtime / "uploads", runtime / "vector_index"):
                if item.is_dir():
                    shutil.rmtree(item)
                elif item.exists():
                    item.unlink()
        runtime.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staging / "research_navigator.db", database)
        for directory in ("uploads", "vector_index"):
            source = staging / directory
            destination = runtime / directory
            if source.exists():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                destination.mkdir(parents=True, exist_ok=True)
    print(runtime)


if __name__ == "__main__":
    main()
