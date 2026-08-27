#!/usr/bin/env python3
"""Export the FastAPI OpenAPI schema without starting external services."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from research_navigator.config import Settings
from research_navigator.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("delivery/OPENAPI.json"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="research-navigator-openapi-") as temp_dir:
        state = Path(temp_dir)
        settings = Settings(
            data_dir=state,
            database_url=f"sqlite+pysqlite:///{(state / 'openapi.db').as_posix()}",
            upload_dir=state / "uploads",
            vector_dir=state / "vectors",
            backup_dir=state / "backups",
            allowed_origins=("http://localhost:5173",),
            enable_fixture_source=False,
            enable_openalex=False,
            enable_crossref=False,
            enable_arxiv=False,
            enable_semantic_scholar=False,
            semantic_scholar_api_key=None,
            unpaywall_email=None,
            crossref_mailto=None,
            llm_base_url=None,
            llm_api_key=None,
            llm_model=None,
            max_pdf_bytes=25 * 1024 * 1024,
            session_ttl_hours=168,
            environment="openapi-export",
        )
        schema = create_app(settings).openapi()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
