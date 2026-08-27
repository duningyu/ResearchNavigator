import json
from pathlib import Path

from sqlalchemy import select
from tests.integration.test_auth_projects import auth_header, make_client, register

from research_navigator.models import SourceRequest


def test_search_persists_source_request_audit_with_provenance(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        user = register(client, "source-audit@example.com")
        headers = auth_header(user)
        response = client.post(
            "/api/search/papers",
            headers=headers,
            json={"query": "anomaly detection", "sources": ["fixture"], "limit": 20},
        )
        assert response.status_code == 200, response.text

        with client.app.state.database.session_factory() as session:  # type: ignore[attr-defined]
            rows = list(session.scalars(select(SourceRequest).order_by(SourceRequest.id)))
        assert len(rows) == 1
        row = rows[0]
        assert row.source == "fixture"
        assert row.query == "anomaly detection"
        assert row.status == "ok"
        assert row.finished_at is not None
        request_meta = json.loads(row.request_json)
        response_meta = json.loads(row.response_metadata_json)
        records = json.loads(row.source_records_json)
        assert request_meta["limit"] >= 20
        assert response_meta["result_count"] >= 1
        assert response_meta["raw_response_hash"]
        assert (
            response_meta["audit_semantics"]
            == "aggregate hash of persisted per-record raw hashes; "
            "not a byte-for-byte HTTP body hash"
        )
        assert records
        assert all(item["source_id"] for item in records)
        assert all("raw_hash" in item for item in records)
        assert all(item["fetched_at"] for item in records)
