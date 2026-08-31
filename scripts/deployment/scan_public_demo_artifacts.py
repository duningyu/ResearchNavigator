"""Fail closed when a built public frontend contains common secrets or local paths."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SECRET_NAMES = (
    "OPENALEX_API_KEY",
    "SEMANTIC_SCHOLAR_API_KEY",
    "LLM_API_KEY",
    "VERCEL_TOKEN",
    "MCP_TOKEN",
    "AUTHORIZATION_TOKEN",
)
WINDOWS_PATH = re.compile(r"(?i)(?<![a-z0-9])[a-z]:\\")
TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".map", ".svg", ".txt"}


def scan(root: Path) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    scanned_files = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        scanned_files += 1
        content = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(root).as_posix()
        if any(name in content for name in SECRET_NAMES):
            findings.append({"path": relative, "kind": "FORBIDDEN_SECRET_NAME"})
        if WINDOWS_PATH.search(content):
            findings.append({"path": relative, "kind": "WINDOWS_ABSOLUTE_PATH"})
    return {
        "status": "PASS" if not findings else "FAIL",
        "root": str(root),
        "scanned_files": scanned_files,
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"Scan root is not a directory: {root}")
    receipt = scan(root)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
