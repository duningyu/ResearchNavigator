import json
import sqlite3
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest


def _valid_sqlite(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE example (id INTEGER PRIMARY KEY)")
        connection.commit()


def test_restore_validation_rejects_path_traversal(tmp_path: Path) -> None:
    from scripts.restore import validate_backup

    database = tmp_path / "db.sqlite"
    _valid_sqlite(database)
    archive = tmp_path / "unsafe.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zipped:
        zipped.write(database, "research_navigator.db")
        zipped.writestr("backup-manifest.json", json.dumps({"format_version": 2}))
        zipped.writestr("../escape.txt", "unsafe")

    with pytest.raises(ValueError, match="Unsafe archive path"):
        validate_backup(archive, tmp_path / "stage")


def test_restore_validation_requires_sqlite_integrity(tmp_path: Path) -> None:
    from scripts.restore import validate_backup

    archive = tmp_path / "broken.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zipped:
        zipped.writestr("research_navigator.db", b"not sqlite")
        zipped.writestr("backup-manifest.json", json.dumps({"format_version": 2}))

    with pytest.raises(ValueError, match="SQLite"):
        validate_backup(archive, tmp_path / "stage")
