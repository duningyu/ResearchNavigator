"""Reusable HTTP idempotency contract for replayable user mutations."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.models import IdempotencyRecord


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _request_hash(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


def replay_snapshot(
    session: Session,
    *,
    request: Request,
    user_id: int,
    operation: str,
    payload: object,
) -> dict[str, Any] | None:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        return None
    if len(key) > 160:
        raise HTTPException(status_code=400, detail="Idempotency-Key is too long")
    request_hash = _request_hash(payload)
    row = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == key,
        )
    )
    if row is None:
        return None
    if row.request_hash != request_hash:
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key was already used with a different request payload",
        )
    snapshot: dict[str, Any] = json.loads(row.response_snapshot_json)
    return snapshot


def store_snapshot(
    session: Session,
    *,
    request: Request,
    user_id: int,
    operation: str,
    payload: object,
    resource_type: str,
    resource_id: str | int,
    response_snapshot: dict[str, Any],
) -> None:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        return
    row = IdempotencyRecord(
        user_id=user_id,
        operation=operation,
        idempotency_key=key,
        request_hash=_request_hash(payload),
        resource_type=resource_type,
        resource_id=str(resource_id),
        scenario_version=request.headers.get("X-Scenario-Version"),
        response_snapshot_json=_canonical(response_snapshot),
    )
    session.add(row)
    session.commit()
