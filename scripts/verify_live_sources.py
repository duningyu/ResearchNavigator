#!/usr/bin/env python3
"""Smoke live scholarly sources without assuming stable titles or result counts."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from research_navigator.scholarly.arxiv import ArxivAdapter
from research_navigator.scholarly.base import ScholarlyAdapter, SearchRequest
from research_navigator.scholarly.crossref import CrossrefAdapter
from research_navigator.scholarly.normalize import deduplicate_records
from research_navigator.scholarly.openalex import OpenAlexAdapter
from research_navigator.scholarly.semantic_scholar import SemanticScholarAdapter


def _record_identity(record) -> dict[str, object]:
    provenance = []
    for item in record.source_provenance:
        provenance.append(
            {
                "source": item.source,
                "source_id": item.source_id,
                "source_url": item.source_url,
                "fetched_at": item.fetched_at.isoformat(),
                "raw_hash": item.raw_hash,
                "is_fixture": item.is_fixture,
            }
        )
    return {
        "doi": record.doi,
        "arxiv_id": record.arxiv_id,
        "external_ids": record.external_ids,
        "source_urls": record.source_urls,
        "provenance": provenance,
    }


async def execute(query: str, limit: int) -> dict[str, object]:
    request = SearchRequest(query=query, limit=limit)
    adapters: list[ScholarlyAdapter] = [
        OpenAlexAdapter(
            mailto=os.getenv("CROSSREF_MAILTO") or None,
            api_key=os.getenv("OPENALEX_API_KEY") or None,
        ),
        CrossrefAdapter(mailto=os.getenv("CROSSREF_MAILTO") or None),
        ArxivAdapter(),
        SemanticScholarAdapter(api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY") or None),
    ]
    report: dict[str, object] = {
        "query": query,
        "requested_limit_per_source": limit,
        "started_at": datetime.now(UTC).isoformat(),
        "acceptance_rule": (
            "Source must return status=ok and at least one record with stable source identifier "
            "and raw hash. "
            "Titles and counts are intentionally not frozen because live scholarly sources change."
        ),
        "sources": [],
    }
    all_records = []
    failures: list[str] = []
    for adapter in adapters:
        result = await adapter.search(request)
        source_entry: dict[str, object] = {
            "source": adapter.name,
            "status": result.status.status,
            "detail": result.status.detail,
            "checked_at": result.status.checked_at.isoformat(),
            "result_count": len(result.records),
            "identifiers": [_record_identity(record) for record in result.records],
        }
        source_ok = result.status.status == "ok" and bool(result.records)
        if source_ok:
            for record in result.records:
                for provenance in record.source_provenance:
                    if (
                        provenance.source != adapter.name
                        or provenance.is_fixture
                        or not provenance.source_id
                        or not provenance.raw_hash
                    ):
                        source_ok = False
                        break
                if not source_ok:
                    break
        source_entry["acceptance"] = "PASS" if source_ok else "FAIL"
        if not source_ok:
            failures.append(adapter.name)
        all_records.extend(result.records)
        report["sources"].append(source_entry)
    deduplicated = deduplicate_records(all_records)
    report["dedup"] = {"input_count": len(all_records), "output_count": len(deduplicated)}
    report["finished_at"] = datetime.now(UTC).isoformat()
    report["overall_status"] = "PASS" if not failures else "FAIL"
    report["failed_sources"] = failures
    return report


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="attention")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = await execute(args.query, args.limit)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    if report["overall_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
