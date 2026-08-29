#!/usr/bin/env python3
"""Create a clean ResearchNavigator source ZIP with reproducible manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

try:
    from scripts.release_metadata import PACKAGE_NAME, PACKAGE_VERSION, RELEASE_LABEL
except ModuleNotFoundError:  # Direct ``python scripts/<name>.py`` invocation.
    from release_metadata import PACKAGE_NAME, PACKAGE_VERSION, RELEASE_LABEL

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "playwright-report",
    "test-results",
    ".idea",
    ".vscode",
}
EXCLUDED_NAMES = {".env", ".DS_Store", "Thumbs.db", ".coverage"}
REGENERATED_DELIVERY = {
    Path("delivery/FILE_MANIFEST.json"),
    Path("delivery/SHA256SUMS.txt"),
    Path("delivery/PACKAGE_INFO.json"),
    Path("delivery/GIT_LOG.txt"),
    Path("delivery/SOURCE_TREE.txt"),
}


def should_exclude(relative: Path) -> bool:
    if relative in REGENERATED_DELIVERY:
        return True
    if relative.name in EXCLUDED_NAMES:
        return True
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return True
    if relative.suffix in {".pyc", ".pyo"}:
        return True
    if relative.parts and relative.parts[0] == "runtime":
        return relative != Path("runtime/.gitkeep")
    if relative.parts and relative.parts[0] in {"uploads", "vector_index", "backups"}:
        return True
    if "uploads" in relative.parts or relative.suffix.lower() == ".pdf":
        return True
    return relative.suffix in {".db", ".sqlite3"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return f"git {' '.join(args)} failed: {result.stderr.strip()}"
    return result.stdout.rstrip() + "\n"


def copy_source(destination: Path) -> int:
    count = 0
    for source in sorted(ROOT.rglob("*")):
        relative = source.relative_to(ROOT)
        if should_exclude(relative):
            continue
        target = destination / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if source.is_symlink():
            raise RuntimeError(f"Refusing to package symlink: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        count += 1
    return count


def write_evidence(destination: Path, *, copied_files: int) -> dict[str, object]:
    delivery = destination / "delivery"
    delivery.mkdir(parents=True, exist_ok=True)
    commit = git_output("rev-parse", "HEAD").strip()
    branch = git_output("branch", "--show-current").strip()
    status = git_output("status", "--short").strip()
    git_log = (
        f"HEAD: {commit}\nBRANCH: {branch}\nWORKING_TREE_AT_PACKAGE_TIME:\n"
        f"{status or '(clean)'}\n\nRECENT_COMMITS:\n"
        f"{git_output('--no-pager', 'log', '--oneline', '-25')}"
    )
    (delivery / "GIT_LOG.txt").write_text(git_log)

    tree_paths = [
        path.relative_to(destination).as_posix()
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    ]
    (delivery / "SOURCE_TREE.txt").write_text("\n".join(tree_paths) + "\n")

    info: dict[str, object] = {
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "release_label": RELEASE_LABEL,
        "packaged_at_utc": datetime.now(UTC).isoformat(),
        "source_commit": commit,
        "source_branch": branch,
        "source_working_tree_at_package_time": status,
        "copied_file_count_before_generated_evidence": copied_files,
        "runtime_user_data_included": False,
        "git_directory_included": False,
        "secrets_included": False,
        "claim": (
            f"{RELEASE_LABEL} source delivery; see STATUS.json, TEST_REPORT.md, and "
            "GAP_LEDGER.csv for executed versus blocked gates."
        ),
    }
    (delivery / "PACKAGE_INFO.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n"
    )

    manifest_entries = []
    for path in sorted(destination.rglob("*")):
        if not path.is_file() or path.name in {"FILE_MANIFEST.json", "SHA256SUMS.txt"}:
            continue
        relative = path.relative_to(destination).as_posix()
        manifest_entries.append(
            {"path": relative, "size_bytes": path.stat().st_size, "sha256": sha256(path)}
        )
    manifest = {
        "format_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "file_count": len(manifest_entries),
        "files": manifest_entries,
    }
    manifest_path = delivery / "FILE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    checksum_paths = [
        path
        for path in sorted(destination.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.txt"
    ]
    checksum_lines = [
        f"{sha256(path)}  {path.relative_to(destination).as_posix()}" for path in checksum_paths
    ]
    (delivery / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n")
    info["manifest_file_count"] = len(manifest_entries)
    info["checksum_line_count"] = len(checksum_lines)
    return info


def create_zip(source: Path, output: Path) -> int:
    count = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            archive.write(path, (Path(source.name) / path.relative_to(source)).as_posix())
            count += 1
    with ZipFile(output) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"ZIP integrity failure at {bad}")
        if len(archive.namelist()) != count:
            raise RuntimeError("ZIP entry count mismatch")
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    default_name = (
        f"ResearchNavigator_{PACKAGE_VERSION}_{RELEASE_LABEL}_"
        f"{datetime.now(UTC).date().isoformat()}"
    )
    parser.add_argument("--name", default=default_name)
    parser.add_argument("--output-dir", type=Path, default=Path("/mnt/data"))
    parser.add_argument("--keep-staging", action="store_true")
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    staging = output_dir / args.name
    archive = output_dir / f"{args.name}.zip"
    if staging.exists():
        shutil.rmtree(staging)
    if archive.exists():
        archive.unlink()
    staging.mkdir(parents=True)

    copied = copy_source(staging)
    info = write_evidence(staging, copied_files=copied)
    entries = create_zip(staging, archive)
    result = {
        **info,
        "staging_path": str(staging),
        "archive_path": str(archive),
        "archive_size_bytes": archive.stat().st_size,
        "archive_sha256": sha256(archive),
        "zip_entry_count": entries,
        "zip_integrity": "PASS",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.keep_staging:
        shutil.rmtree(staging)


if __name__ == "__main__":
    main()
