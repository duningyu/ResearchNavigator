"""Consistent runtime backup plus restart-bound staged restore."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from sqlalchemy.engine import make_url

from research_navigator.config import Settings


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def database_path(settings: Settings) -> Path:
    url = make_url(settings.database_url)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        raise ValueError("Backup/restore currently requires a file-backed SQLite database")
    return Path(url.database).expanduser().resolve()


def backup_info(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "name": path.name,
        "size_bytes": stat.st_size,
        "sha256": _sha256(path),
        "created_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
    }


def create_backup(settings: Settings) -> dict[str, object]:
    settings.ensure_directories()
    source_db = database_path(settings)
    if not source_db.is_file():
        raise FileNotFoundError(f"Database not found: {source_db}")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output = settings.backup_dir / f"research-navigator-{timestamp}.zip"
    with tempfile.TemporaryDirectory() as temp_dir:
        snapshot = Path(temp_dir) / "research_navigator.db"
        source_conn = sqlite3.connect(source_db)
        target_conn = sqlite3.connect(snapshot)
        try:
            source_conn.backup(target_conn)
        finally:
            # Windows locks open files, so the snapshot handle must be closed
            # before TemporaryDirectory cleanup; sqlite3's context manager
            # only manages transactions and never closes the connection.
            target_conn.close()
            source_conn.close()
        manifest = {
            "format_version": 2,
            "created_at": datetime.now(UTC).isoformat(),
            "database_filename": source_db.name,
            "upload_dirname": settings.upload_dir.name,
            "vector_dirname": settings.vector_dir.name,
        }
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            archive.write(snapshot, "research_navigator.db")
            for label, root in (
                ("uploads", settings.upload_dir),
                ("vector_index", settings.vector_dir),
            ):
                if root.exists():
                    for path in sorted(root.rglob("*")):
                        if path.is_file():
                            archive.write(path, f"{label}/{path.relative_to(root).as_posix()}")
            archive.writestr(
                "backup-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
            )
    return backup_info(output)


def list_backups(settings: Settings) -> list[dict[str, object]]:
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    return [
        backup_info(path)
        for path in sorted(
            settings.backup_dir.glob("*.zip"), key=lambda value: value.stat().st_mtime, reverse=True
        )
    ]


def _safe_backup_path(settings: Settings, name: str) -> Path:
    if Path(name).name != name or not name.endswith(".zip"):
        raise ValueError("Invalid backup name")
    path = (settings.backup_dir / name).resolve()
    if path.parent != settings.backup_dir.resolve() or not path.is_file():
        raise FileNotFoundError("Backup not found")
    return path


def stage_restore(settings: Settings, name: str) -> dict[str, object]:
    backup = _safe_backup_path(settings, name)
    staging_root = settings.data_dir / ".restore-staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    staging = staging_root / uuid.uuid4().hex
    staging.mkdir(parents=True)
    try:
        with ZipFile(backup) as archive:
            names = {member.filename for member in archive.infolist()}
            if "research_navigator.db" not in names or "backup-manifest.json" not in names:
                raise ValueError("Backup is missing database or manifest")
            for member in archive.infolist():
                target = (staging / member.filename).resolve()
                if staging.resolve() not in target.parents and target != staging.resolve():
                    raise ValueError(f"Unsafe archive path: {member.filename}")
            archive.extractall(staging)
            manifest = json.loads((staging / "backup-manifest.json").read_text(encoding="utf-8"))
            if int(manifest.get("format_version", 0)) not in {1, 2}:
                raise ValueError("Unsupported backup format version")
        with sqlite3.connect(staging / "research_navigator.db") as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise ValueError("Staged SQLite integrity check failed")
    except (BadZipFile, OSError, json.JSONDecodeError, sqlite3.DatabaseError, ValueError):
        shutil.rmtree(staging, ignore_errors=True)
        raise
    marker = {
        "backup_name": backup.name,
        "backup_sha256": _sha256(backup),
        "staging_path": str(staging),
        "staged_at": datetime.now(UTC).isoformat(),
    }
    marker_path = settings.data_dir / "pending_restore.json"
    marker_path.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**marker, "restart_required": True}


def apply_pending_restore(settings: Settings) -> dict[str, object] | None:
    marker_path = settings.data_dir / "pending_restore.json"
    if not marker_path.exists():
        return None
    marker: dict[str, object] = json.loads(marker_path.read_text(encoding="utf-8"))
    staging = Path(str(marker["staging_path"])).resolve()
    allowed_root = (settings.data_dir / ".restore-staging").resolve()
    if allowed_root not in staging.parents or not staging.is_dir():
        raise RuntimeError("Pending restore staging path is invalid")
    staged_db = staging / "research_navigator.db"
    if not staged_db.is_file():
        raise RuntimeError("Pending restore database is missing")
    destination_db = database_path(settings)
    destination_db.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("-wal", "-shm"):
        Path(f"{destination_db}{suffix}").unlink(missing_ok=True)
    temp_db = destination_db.with_suffix(destination_db.suffix + ".restore-tmp")
    shutil.copy2(staged_db, temp_db)
    temp_db.replace(destination_db)
    for source_name, destination in (
        ("uploads", settings.upload_dir),
        ("vector_index", settings.vector_dir),
    ):
        staged_dir = staging / source_name
        if destination.exists():
            shutil.rmtree(destination)
        if staged_dir.exists():
            shutil.copytree(staged_dir, destination)
        else:
            destination.mkdir(parents=True, exist_ok=True)
    marker_path.unlink(missing_ok=True)
    shutil.rmtree(staging, ignore_errors=True)
    return marker
